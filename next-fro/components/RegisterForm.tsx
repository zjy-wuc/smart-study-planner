
"use client";

import { useState } from "react";//保存输入内容
import { registerUser } from "@/services/auth.service";
import type { RegisterRequest } from "@/types/auth";

export default function RegisterForm() {
  const [formData, setFormData] = useState<RegisterRequest>({
    username: "",
    password: "",
    nickname: "",
  });

  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(
    event: React.FormEvent<HTMLFormElement>
  ) {
    event.preventDefault();//阻止表单默认提交行为

    setLoading(true);
    setMessage("");//清空上一次提示信息

    try {
      const result = await registerUser(formData);

      setMessage(`注册成功，欢迎你，${result.data.nickname}！`);

      setFormData({
        username: "",
        password: "",
        nickname: "",
      });
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "注册失败"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h2>用户注册</h2>

      <div>
        <label>用户名</label>
        <input
          value={formData.username}//输入框显示的内容
          onChange={(event) =>//监听用户输入
            setFormData({
              ...formData,
              username: event.target.value,
            })
          }
          required
        />
      </div>

      <div>
        <label>密码</label>
        <input
          type="password"
          value={formData.password}
          onChange={(event) =>
            setFormData({
              ...formData,
              password: event.target.value,
            })
          }
          required
        />
      </div>

      <div>
        <label>昵称</label>
        <input
          value={formData.nickname}
          onChange={(event) =>
            setFormData({
              ...formData,
              nickname: event.target.value,
            })
          }
          required
        />
      </div>

      <button type="submit" disabled={loading}>
        {loading ? "注册中..." : "注册"}
      </button>

      {/* message 有内容时才显示提示信息 */}
      {message && <p>{message}</p>}
    </form>
  );
}
