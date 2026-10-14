import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { Button, Dialog, Field, Input, Select, TextArea } from "./ui";
import { Bi, useBi } from "../i18n";
import { useToast } from "./ui/Toast";

type VehicleOption = { id: string; label: string };

export function InquiryDialog({
  open,
  onClose,
  vehicleId,
  vehicleLabel,
  vehicles,
}: {
  open: boolean;
  onClose: () => void;
  vehicleId?: string;
  vehicleLabel?: string;
  vehicles?: VehicleOption[];
}) {
  const bi = useBi();
  const toast = useToast();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [note, setNote] = useState("");
  const [picked, setPicked] = useState(vehicleId ?? "");

  const save = useMutation({
    mutationFn: () =>
      api.cases.inquiry({
        vehicle_id: vehicleId ?? picked,
        full_name: fullName.trim(),
        phone: phone.trim(),
        note: note.trim(),
      }),
    onSuccess: () => {
      toast(bi("Inquiry sent to the team.", "استعلام برای تیم ثبت شد."));
      setFullName("");
      setPhone("");
      setNote("");
      onClose();
    },
    onError: (error: Error) => toast(error.message),
  });

  const targetId = vehicleId ?? picked;

  if (!open) return null;

  return (
    <Dialog onClose={onClose} label={bi("New buyer inquiry", "استعلام جدید")}>
      <div className="stack">
        {vehicleLabel ? (
          <p className="muted">
            <Bi en="Vehicle" fa="خودرو" />: {vehicleLabel}
          </p>
        ) : null}
        {vehicles && vehicles.length > 0 ? (
          <Field label={bi("Vehicle", "خودرو")}>
            <Select value={picked} onChange={(event) => setPicked(event.target.value)}>
              <option value="">{bi("Choose…", "انتخاب…")}</option>
              {vehicles.map((row) => (
                <option key={row.id} value={row.id}>{row.label}</option>
              ))}
            </Select>
          </Field>
        ) : null}
        <Field label={bi("Buyer name", "نام خریدار")}>
          <Input value={fullName} onChange={(event) => setFullName(event.target.value)} />
        </Field>
        <Field label={bi("Phone", "تلفن")}>
          <Input value={phone} onChange={(event) => setPhone(event.target.value)} dir="ltr" />
        </Field>
        <Field label={bi("Note", "یادداشت")}>
          <TextArea value={note} onChange={(event) => setNote(event.target.value)} rows={3} />
        </Field>
        <div className="row">
          <Button
            type="button"
            disabled={save.isPending || !targetId || !fullName.trim() || !phone.trim()}
            onClick={() => save.mutate()}
          >
            <Bi en="Save inquiry" fa="ثبت استعلام" />
          </Button>
          <Button type="button" variant="secondary" onClick={onClose}>
            <Bi en="Cancel" fa="انصراف" />
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
