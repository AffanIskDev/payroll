import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(false));
  }, []);

  // akun RUSA sendiri (3 Nov 2026): peran & akses dari daftar pengguna RUSA; kata sandi RUSA atau ROSY menurut penggunanya
  const refresh = () => api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(false));

  const login = async (username, password) => {
    const { data } = await api.post("/auth/login", { username, password });
    localStorage.setItem("payroll_token", data.token);
    setUser(data.user);
    return data.user;
  };

  // Multi-PT (6 Nov 2026): ganti PT aktif = token baru untuk PT itu. Muat ulang penuh supaya semua data di layar milik PT baru.
  const gantiPt = async (companyId) => {
    const { data } = await api.post("/auth/pt", { company_id: companyId });
    localStorage.setItem("payroll_token", data.token);
    window.location.assign("/hr-manager");
  };

  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    localStorage.removeItem("payroll_token");
    setUser(false);
  };

  return <AuthCtx.Provider value={{ user, login, logout, refresh, gantiPt }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
export const ROLE_LABELS = { master_admin: "Master Admin", manager_hrd: "Manager HRD", supervisor: "Supervisor HRD" };
export const isHr = (u) => !!u && ["manager_hrd", "supervisor"].includes(u.role);
export const isManager = (u) => !!u && u.role === "manager_hrd";
// Master Admin (3 Nov 2026): hanya mengatur pengguna & akses RUSA, tanpa akses data gaji
export const isMasterAdmin = (u) => !!u && u.role === "master_admin";
