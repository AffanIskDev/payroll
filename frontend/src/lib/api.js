import axios from "axios";

export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`, withCredentials: true });

api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem("payroll_token");
  if (t) cfg.headers.Authorization = `Bearer ${t}`;
  return cfg;
});

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || "Terjadi kesalahan";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  return String(d);
}

export async function downloadBlob(url, filename, open = false) {
  const res = await api.get(url, { responseType: "blob" });
  const href = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
  if (open) {
    window.open(href, "_blank");
    return;
  }
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
}

export async function saveFile(method, url, fallbackName) {
  const res = await api.request({ method, url, responseType: "blob" });
  const cd = res.headers["content-disposition"] || "";
  const name = (cd.match(/filename="?([^"]+)"?/) || [])[1] || fallbackName;
  const href = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
  URL.revokeObjectURL(href);
  return res.headers;
}

export async function blobErrMsg(e) {
  const d = e?.response?.data;
  if (d instanceof Blob) {
    try { return JSON.parse(await d.text()).detail || "Terjadi kesalahan"; } catch { return "Terjadi kesalahan"; }
  }
  return errMsg(e);
}
