import axios from "axios";

const client = axios.create({
  baseURL: "http://localhost:8001/api/v1",
  timeout: 30000,
});

export default client;
