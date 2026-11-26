import React from "react";
import { AuthProvider } from "./context/AuthContext";
import { RouterProvider, useRouter } from "./lib/router";
import { SiteLayout } from "./components/SiteLayout";
import { LandingPage } from "./pages/LandingPage";
import { PricingPage } from "./pages/PricingPage";
import {
  AuthCallbackPage,
  ForgotPasswordPage,
  SignInPage,
  SignUpPage,
  VerifyEmailPage,
} from "./pages/AuthPages";
import { AccountSubscriptionPage } from "./pages/AccountSubscriptionPage";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import {
  ContactPage,
  DocsPage,
  PrivacyPolicyPage,
  RiskDisclosurePage,
  TermsOfServicePage,
} from "./pages/LegalAndDocsPages";

const AppRoutes: React.FC = () => {
  const { pathname } = useRouter();
  const clean = pathname.replace(/\/+$/, "") || "/";

  switch (clean) {
    case "/":
      return <LandingPage />;
    case "/pricing":
      return <PricingPage />;
    case "/docs":
      return <DocsPage />;
    case "/auth":
    case "/auth/sign-in":
      return <SignInPage />;
    case "/auth/sign-up":
      return <SignUpPage />;
    case "/auth/forgot-password":
      return <ForgotPasswordPage />;
    case "/auth/verify-email":
      return <VerifyEmailPage />;
    case "/auth/callback":
      return <AuthCallbackPage />;
    case "/account":
    case "/account/subscription":
      return <AccountSubscriptionPage />;
    case "/admin":
      return <AdminDashboardPage />;
    case "/legal/terms":
      return <TermsOfServicePage />;
    case "/legal/privacy":
      return <PrivacyPolicyPage />;
    case "/legal/risk-disclosure":
      return <RiskDisclosurePage />;
    case "/contact":
      return <ContactPage />;
    default:
      return <LandingPage />;
  }
};

export default function App(): React.ReactElement {
  return (
    <RouterProvider>
      <AuthProvider>
        <SiteLayout>
          <AppRoutes />
        </SiteLayout>
      </AuthProvider>
    </RouterProvider>
  );
}
