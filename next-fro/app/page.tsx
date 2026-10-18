
"use client";

import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
};

export default function Home() {
  const [status, setStatus] = useState("正在连接后端...");
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("http://127.0.0.1:8000/health")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP 错误：${response.status}`);
        }
        return response.json();
      })
      .then((data: HealthResponse) => {
        setStatus(data.status);
      })
      .catch((err: Error) => {
        setError(err.message);
        setStatus("连接失败");
      });
  }, []);

  return (
    <main style={{ maxWidth: 700, margin: "80px auto", padding: 24 }}>
      <h1>智能学习计划管理系统</h1>
      <p>前端：Next.js</p>
      <p>后端：Python + FastAPI</p>

      <hr />

      <h2>后端连接测试</h2>
      <p>连接状态：{status}</p>

      {error && (
        <p style={{ color: "red" }}>
          错误信息：{error}
        </p>
      )}
    </main>
  );
}
