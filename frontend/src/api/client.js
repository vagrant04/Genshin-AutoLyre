import axios from "axios";

const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const client = axios.create({ baseURL, timeout: 30_000 });

client.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response && err.response.data && err.response.data.message) {
      err.userMessage = err.response.data.message;
    } else {
      err.userMessage = "服务暂时不可用，请稍后重试。";
    }
    return Promise.reject(err);
  }
);

export async function searchMusic(query, limit = 5) {
  const resp = await client.get("/api/search", { params: { q: query, limit } });
  return resp.data;
}

export async function parseResource({ result_id, download_url, title, source }) {
  const resp = await client.post("/api/parse", { result_id, download_url, title, source });
  return resp.data;
}

export async function uploadMidi(file) {
  const form = new FormData();
  form.append("file", file);
  const resp = await client.post("/api/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

export async function generateScore({ file_token, title, track_roles }) {
  const resp = await client.post("/api/generate", { file_token, title, track_roles });
  return resp.data;
}

export async function getPreviewTrack(fileToken, trackIndex, mapped) {
  const resp = await client.get("/api/preview-track", {
    params: { file_token: fileToken, track_index: trackIndex, mapped },
  });
  return resp.data;
}

export default client;
