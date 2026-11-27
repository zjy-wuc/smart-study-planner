"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { ApiError, restoreAccessToken } from "@/lib/api/client";
import {
  authEpoch,
  onAuthMessage,
  sameAuthEpoch,
} from "@/lib/auth/coordinator";
import {
  clearAccessToken,
  clearLegacyTokens,
  getAccessToken,
  getAuthGeneration,
  subscribeAuth,
} from "@/lib/auth/token";
import { getCurrentUser } from "@/services/auth.service";
import type { User } from "@/types/auth";

type AuthState =
  | "loading"
  | "authenticated"
  | "unauthenticated"
  | "temporary-error";
type AuthValue = {
  status: AuthState;
  user: User | null;
  completeLogin: (user: User) => void;
  updateUser: (user: User) => void;
  clear: () => void;
  retry: () => void;
};
const AuthContext = createContext<AuthValue | null>(null);
let restorePromise: Promise<User> | null = null;
let restoreEpoch: string | null = null;
let restoreGeneration = 0;

function restoreUser(epoch: string | null, generation: number): Promise<User> {
  if (
    !restorePromise ||
    restoreEpoch !== epoch ||
    restoreGeneration !== generation
  ) {
    const pending = (async () => {
      await restoreAccessToken();
      return (await getCurrentUser()).data;
    })();
    const tracked = pending.finally(() => {
      if (restorePromise === tracked) restorePromise = null;
    });
    restorePromise = tracked;
    restoreEpoch = epoch;
    restoreGeneration = generation;
  }
  return restorePromise;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let live = true;
    let epoch: string | null;
    try {
      clearLegacyTokens();
      epoch = authEpoch();
    } catch {
      queueMicrotask(() => {
        setUser(null);
        setStatus("temporary-error");
      });
      return;
    }
    const generation = getAuthGeneration();
    const stillCurrent = () => {
      if (!live) return false;
      try { return sameAuthEpoch(epoch) && getAuthGeneration() === generation; }
      catch {
        setUser(null);
        setStatus("temporary-error");
        return false;
      }
    };
    void restoreUser(epoch, generation)
      .then((restored) => {
        if (stillCurrent()) {
          setUser(restored);
          setStatus("authenticated");
        }
      })
      .catch((error: unknown) => {
        if (!stillCurrent()) return;
        setUser(null);
        const confirmed = error instanceof ApiError && (
          error.status === 401 || error.code === "ACCOUNT_DISABLED"
        );
        setStatus(confirmed ? "unauthenticated" : "temporary-error");
      });
    return () => {
      live = false;
    };
  }, [revision]);

  useEffect(
    () =>
      onAuthMessage((type) => {
        clearAccessToken();
        setUser(null);
        if (type === "logout") setStatus("unauthenticated");
        else {
          setStatus("loading");
          setRevision((value) => value + 1);
        }
      }),
    [],
  );

  useEffect(
    () =>
      subscribeAuth(() => {
        try {
          if (getAccessToken()) return;
          setUser(null);
          setStatus("unauthenticated");
        } catch {
          setUser(null);
          setStatus("temporary-error");
        }
      }),
    [],
  );

  return (
    <AuthContext.Provider
      value={{
        status,
        user,
        completeLogin: (next) => {
          setUser(next);
          setStatus("authenticated");
        },
        updateUser: (next) => setUser(next),
        clear: () => {
          clearAccessToken();
          setUser(null);
          setStatus("unauthenticated");
        },
        retry: () => {
          setStatus("loading");
          setRevision((value) => value + 1);
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("AuthProvider is missing");
  return context;
}
