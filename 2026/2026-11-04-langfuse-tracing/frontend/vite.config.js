export default {
  server: {
    proxy: {
      '/ask': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
};
