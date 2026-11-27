import LoginForm from "@/components/auth/LoginForm";
import AuthScene from "@/components/auth/AuthScene";
import "@/components/css/LoginForm.css";

export default function LoginPage() {
  return <main className="login-page"><LoginForm /><AuthScene /></main>;
}
