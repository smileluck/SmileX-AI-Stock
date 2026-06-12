import axios from "axios";

const client = axios.create({
  baseURL: "http://localhost:8801/api/v1",
  timeout: 30000,
});

export default client;
