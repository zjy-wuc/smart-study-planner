import RegisterForm from "@/components/RegisterForm";
import AuthScene from "@/components/auth/AuthScene";
import "@/components/css/LoginForm.css";

export default function RegisterPage() {
  return (
    <main className="login-page">
      <RegisterForm />
      <AuthScene />
    </main>
  );
}
