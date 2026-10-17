import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api";
import { Button, Card, ErrorMessage, Field, Input } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { Bi, useBi } from "../../i18n";
import { queryKeys } from "../../lib/queryKeys";

export function TotpCard() {
  const toast = useToast();
  const bi = useBi();
  const qc = useQueryClient();
  const [secret, setSecret] = useState("");
  const [otpauth, setOtpauth] = useState("");
  const [code, setCode] = useState("");

  const reveal = useMutation({
    mutationFn: () => api.totp.setup(),
    onSuccess: (row) => {
      setSecret(row.secret);
      setOtpauth(row.otpauth);
    },
    onError: () => {
      toast(bi("Could not load the secret", "دریافت رمز ناموفق بود"));
    },
  });

  const enable = useMutation({
    mutationFn: () => api.totp.enable(code),
    onSuccess: () => {
      setCode("");
      setSecret("");
      setOtpauth("");
      void qc.invalidateQueries({ queryKey: queryKeys.telegramStatus });
      toast(bi("Two-factor login enabled", "ورود دو مرحله‌ای فعال شد"));
    },
    onError: () => {
      toast(bi("Invalid code", "کد نامعتبر است"));
    },
  });

  return (
    <Card>
      <h2>
        <Bi en="Two-factor login" fa="ورود دو مرحله‌ای" />
      </h2>
      {!otpauth ? (
        <Button variant="secondary" disabled={reveal.isPending} onClick={() => reveal.mutate()}>
          <Bi en="Show secret" fa="نمایش رمز" />
        </Button>
      ) : (
        <>
          <p>
            <Bi
              en="Add this key to your authenticator app, then enter the 6-digit code it shows."
              fa="این کلید را در اپ احراز هویت خود ثبت کنید، سپس کد ۶ رقمی آن را وارد کنید."
            />
          </p>
          <p className="mono ltr-value">{secret}</p>
          <details>
            <summary>
              <Bi en="Show setup URI" fa="نمایش URI راه‌اندازی" />
            </summary>
            <p className="mono ltr-value">{otpauth}</p>
          </details>
          <Field label={<Bi en="6-digit code" fa="کد ۶ رقمی" />}>
            <Input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              pattern="[0-9]{6}"
              placeholder="000000"
              disabled={enable.isPending}
            />
          </Field>
          <ErrorMessage error={enable.isError ? String((enable.error as Error).message) : ""} />
          <Button onClick={() => enable.mutate()} disabled={enable.isPending || !/^[0-9]{6}$/.test(code)}>
            {enable.isPending ? <Bi en="Enabling…" fa="در حال فعال‌سازی…" /> : <Bi en="Enable" fa="فعال‌سازی" />}
          </Button>
        </>
      )}
    </Card>
  );
}
