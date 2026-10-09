import { createContext, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => setUser(false));
  }, []);

  // username & password ROSY, diverifikasi HAM; peran mengikuti jabatan di ROSY
  const login = async (username, password) => {
    const { data } = await api.post("/auth/login", { username, password });
    localStorage.setItem("payroll_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    localStorage.removeItem("payroll_token");
    setUser(false);
  };

  return <AuthCtx.Provider value={{ user, login, logout }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);
export const ROLE_LABELS = { manager_hrd: "Manager HRD", supervisor: "Supervisor HRD" };
export const isHr = (u) => !!u && ["manager_hrd", "supervisor"].includes(u.role);
export const isManager = (u) => !!u && u.role === "manager_hrd";
