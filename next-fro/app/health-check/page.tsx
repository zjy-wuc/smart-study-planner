"use client";

import { messages } from "@/messages";

import { useEffect, useState } from "react";

type HealthResponse = {
  status: string;
};

export default function Home() {
  const [status, setStatus] = useState(messages.health.connecting);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/health`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(messages.health.httpError(response.status));
        }
        return response.json();
      })
      .then((data: HealthResponse) => {
        setStatus(data.status);
      })
      .catch((err: Error) => {
        setError(err.message);
        setStatus(messages.health.connectionFailed);
      });
  }, []);//组件挂载时执行一次

  return (
    <main style={{ maxWidth: 700, margin: "80px auto", padding: 24 }}>
      <h1>{messages.health.title}</h1>
      <p>{messages.health.frontend}</p>
      <p>{messages.health.backend}</p>

      <hr />

      <h2>{messages.health.testTitle}</h2>
      <p>{messages.health.statusText(status)}</p>

      {error && (
        <p style={{ color: "red" }}>{messages.health.errorText(error)}
        </p>
      )}
    </main>
  );
}
