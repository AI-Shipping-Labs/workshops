# AWS Experiment Account Helper

Small helper scripts for workshop participants who want an isolated AWS account for experiments and temporary credentials for deployment.

The workflow is split into two steps:

1. Create or verify an AWS Organizations member account and admin IAM user.
2. Generate temporary AWS credentials for that account and merge them into an env file.

## Requirements

- AWS CLI or environment credentials with permissions to manage AWS Organizations from the management account.
- `uv`
- Python 3.13+
- `boto3`, installed with `uv sync` or `uv add boto3`

Install dependencies:

```sh
uv sync
```

## Configuration

Copy the example config:

```sh
cp .env.example .env
```

Edit `.env`:

```text
AWS_EXPERIMENTS_ACCOUNT_EMAIL=aws+experiments@example.com
AWS_EXPERIMENTS_ACCOUNT_NAME=experiments
AWS_EXPERIMENTS_OU_NAME=Experiments
AWS_EXPERIMENTS_ADMIN_USER=experiments-admin
AWS_EXPERIMENTS_ACCESS_ROLE_NAME=OrganizationAccountAccessRole
AWS_EXPERIMENTS_MAX_SESSION_DURATION=7200
```

Do not commit `.env`, generated credentials, or initial passwords.

## 1. Set Up Account And User

```sh
uv run python setup_account.py
```

The script:

- finds or creates the configured OU
- finds or creates the configured AWS member account
- moves the account into the OU
- assumes `OrganizationAccountAccessRole`
- creates or verifies the admin IAM user
- attaches `AdministratorAccess`
- creates a console login profile if needed
- prints the live result block to stdout

To rotate or set the admin password:

```sh
uv run python setup_account.py \
  --admin-password '<new-password>' \
  --rotate-password
```

## 2. Generate Temporary Credentials

Write temporary credentials to a local env file:

```sh
uv run python get_temporary_credentials.py \
  --output experiments-env \
  --region eu-west-1 \
  --duration-seconds 7200
```

Merge credentials into a remote env file over SSH:

```sh
uv run python get_temporary_credentials.py \
  --output experiments-env \
  --region eu-west-1 \
  --duration-seconds 7200 \
  --remote-host <ssh-host> \
  --remote-path '~/tmp/lambda-deploy/.env'
```

Remote behavior:

- creates the env file if it does not exist
- appends missing AWS credential variables
- updates existing AWS credential variables
- preserves unrelated variables and comments

The generated env file contains:

```text
AWS_ACCESS_KEY_ID=<temporary-access-key>
AWS_SECRET_ACCESS_KEY=<temporary-secret-key>
AWS_SESSION_TOKEN=<temporary-session-token>
AWS_DEFAULT_REGION=eu-west-1
AWS_REGION=eu-west-1
AWS_ACCOUNT_ID=<account-id>
AWS_CREDENTIAL_EXPIRATION=<expiration>
```

Temporary credentials expire automatically.

## Billing

An AWS Organizations member account uses consolidated billing through the management account. You get account-level cost visibility, but not a separate AWS bill or payment method while the account remains in the organization.
