#!/usr/bin/env python3
"""Create or verify an AWS Organizations experiment account."""


import argparse
import pathlib
import secrets
import string
import sys
import time
from dataclasses import dataclass

import boto3
from botocore.exceptions import ClientError

from config import env, load_experiments_config


ADMIN_POLICY_ARN = "arn:aws:iam::aws:policy/AdministratorAccess"


@dataclass(frozen=True)
class SetupConfig:
    account_email: str
    account_name: str
    ou_name: str
    admin_user: str
    access_role_name: str
    credentials_file: pathlib.Path
    admin_password: str | None
    rotate_password: bool
    max_session_duration: int


def paginated(client, operation_name: str, result_key: str, **kwargs) -> list[dict]:
    paginator = client.get_paginator(operation_name)
    items: list[dict] = []
    for page in paginator.paginate(**kwargs):
        items.extend(page[result_key])
    return items


def get_root_id(org) -> str:
    roots = org.list_roots()["Roots"]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one organization root, found {len(roots)}")
    return roots[0]["Id"]


def find_or_create_ou(org, root_id: str, ou_name: str) -> dict:
    ous = paginated(
        org,
        "list_organizational_units_for_parent",
        "OrganizationalUnits",
        ParentId=root_id,
    )
    for ou in ous:
        if ou["Name"] == ou_name:
            return ou
    return org.create_organizational_unit(ParentId=root_id, Name=ou_name)["OrganizationalUnit"]


def find_account_by_email(org, email: str) -> dict | None:
    accounts = paginated(org, "list_accounts", "Accounts")
    for account in accounts:
        if account["Email"].lower() == email.lower() and account["State"] == "ACTIVE":
            return account
    return None


def create_account(org, config: SetupConfig) -> dict:
    status = org.create_account(
        Email=config.account_email,
        AccountName=config.account_name,
        RoleName=config.access_role_name,
        IamUserAccessToBilling="ALLOW",
    )["CreateAccountStatus"]

    request_id = status["Id"]
    while True:
        status = org.describe_create_account_status(CreateAccountRequestId=request_id)[
            "CreateAccountStatus"
        ]
        state = status["State"]
        if state == "SUCCEEDED":
            return org.describe_account(AccountId=status["AccountId"])["Account"]
        if state == "FAILED":
            reason = status.get("FailureReason", "unknown")
            raise RuntimeError(f"Account creation failed: {reason}")
        time.sleep(10)


def ensure_account_in_ou(org, account_id: str, ou_id: str) -> None:
    parents = org.list_parents(ChildId=account_id)["Parents"]
    if len(parents) != 1:
        raise RuntimeError(f"Expected one parent for account {account_id}, found {len(parents)}")
    source_parent_id = parents[0]["Id"]
    if source_parent_id == ou_id:
        return
    org.move_account(
        AccountId=account_id,
        SourceParentId=source_parent_id,
        DestinationParentId=ou_id,
    )


def assume_account_role(account_id: str, role_name: str):
    sts = boto3.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    last_error: Exception | None = None
    for _ in range(30):
        try:
            role = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName="setup-experiment-account",
            )
            creds = role["Credentials"]
            return boto3.client(
                "iam",
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
            )
        except ClientError as exc:
            last_error = exc
            time.sleep(10)
    raise RuntimeError(f"Could not assume {role_arn}") from last_error


def random_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+[]{}"),
    ]
    rest = [secrets.choice(alphabet) for _ in range(28)]
    chars = required + rest
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def ensure_admin_user(iam, config: SetupConfig) -> tuple[bool, pathlib.Path | None]:
    try:
        iam.get_user(UserName=config.admin_user)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        iam.create_user(UserName=config.admin_user)

    attached = iam.list_attached_user_policies(UserName=config.admin_user)["AttachedPolicies"]
    if not any(policy["PolicyArn"] == ADMIN_POLICY_ARN for policy in attached):
        iam.attach_user_policy(UserName=config.admin_user, PolicyArn=ADMIN_POLICY_ARN)

    try:
        iam.update_role(
            RoleName=config.access_role_name,
            MaxSessionDuration=config.max_session_duration,
        )
    except ClientError:
        pass

    login_exists = True
    try:
        iam.get_login_profile(UserName=config.admin_user)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "NoSuchEntity":
            raise
        login_exists = False

    if login_exists and not config.rotate_password:
        return False, None

    password = config.admin_password or random_password()
    if login_exists:
        iam.update_login_profile(
            UserName=config.admin_user,
            Password=password,
            PasswordResetRequired=False,
        )
    else:
        iam.create_login_profile(
            UserName=config.admin_user,
            Password=password,
            PasswordResetRequired=True,
        )

    if config.admin_password:
        return True, None

    config.credentials_file.write_text(
        "\n".join(
            [
                "AWS experiments account initial admin sign-in details",
                f"IAM username: {config.admin_user}",
                f"Initial password: {password}",
                "Password reset required: yes",
                "",
                "After first sign-in, store the new password in a password manager and delete this file.",
            ]
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    config.credentials_file.chmod(0o600)
    return True, config.credentials_file


def parse_args() -> SetupConfig:
    load_experiments_config()
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-email", default=env("AWS_EXPERIMENTS_ACCOUNT_EMAIL", ""))
    parser.add_argument("--account-name", default=env("AWS_EXPERIMENTS_ACCOUNT_NAME", "experiments"))
    parser.add_argument("--ou-name", default=env("AWS_EXPERIMENTS_OU_NAME", "Experiments"))
    parser.add_argument("--admin-user", default=env("AWS_EXPERIMENTS_ADMIN_USER", "experiments-admin"))
    parser.add_argument(
        "--access-role-name",
        default=env("AWS_EXPERIMENTS_ACCESS_ROLE_NAME", "OrganizationAccountAccessRole"),
    )
    parser.add_argument(
        "--credentials-file",
        default=env("AWS_EXPERIMENTS_CREDENTIALS_FILE", "initial-admin-credentials.txt"),
    )
    parser.add_argument("--admin-password", default=None)
    parser.add_argument("--rotate-password", action="store_true")
    parser.add_argument(
        "--max-session-duration",
        type=int,
        default=int(env("AWS_EXPERIMENTS_MAX_SESSION_DURATION", "7200")),
    )
    args = parser.parse_args()
    if not args.account_email:
        raise SystemExit("AWS_EXPERIMENTS_ACCOUNT_EMAIL is required in .env or --account-email")
    return SetupConfig(
        account_email=args.account_email,
        account_name=args.account_name,
        ou_name=args.ou_name,
        admin_user=args.admin_user,
        access_role_name=args.access_role_name,
        credentials_file=pathlib.Path(args.credentials_file),
        admin_password=args.admin_password,
        rotate_password=args.rotate_password,
        max_session_duration=args.max_session_duration,
    )


def main() -> int:
    config = parse_args()
    org = boto3.client("organizations")
    sts = boto3.client("sts")

    caller = sts.get_caller_identity()
    organization = org.describe_organization()["Organization"]
    root_id = get_root_id(org)
    ou = find_or_create_ou(org, root_id, config.ou_name)
    account = find_account_by_email(org, config.account_email)
    if account is None:
        account = create_account(org, config)
    ensure_account_in_ou(org, account["Id"], ou["Id"])

    iam = assume_account_role(account["Id"], config.access_role_name)
    password_changed, credentials_file = ensure_admin_user(iam, config)
    login_profile = iam.get_login_profile(UserName=config.admin_user)["LoginProfile"]

    print("## Result")
    print()
    print(f"- Management account ID: `{organization['MasterAccountId']}`")
    print(f"- Management account email: `{organization['MasterAccountEmail']}`")
    print(f"- AWS Organization ID: `{organization['Id']}`")
    print(f"- Organization root ID: `{root_id}`")
    print(f"- Experiments OU ID: `{ou['Id']}`")
    print(f"- Experiments account ID: `{account['Id']}`")
    print(f"- Experiments account email: `{account['Email']}`")
    print(f"- Experiments account name: `{account['Name']}`")
    print(f"- Admin IAM user: `{config.admin_user}`")
    print(f"- Admin policy: `{ADMIN_POLICY_ARN}`")
    print(f"- Console sign-in URL: `https://{account['Id']}.signin.aws.amazon.com/console`")
    print(f"- Caller account used for setup: `{caller['Account']}`")
    print(f"- Password reset required: `{login_profile['PasswordResetRequired']}`")
    if credentials_file:
        print(f"- Generated password file: `{credentials_file}`")
    elif password_changed:
        print("- Admin password: updated from provided input")
    else:
        print("- Admin password: unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
