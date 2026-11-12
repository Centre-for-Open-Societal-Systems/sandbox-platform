import { Badge } from "@/components/ui/badge";
import type { PartnerKeyInfo } from "@/types/api";

function day(iso: string): string {
  return iso.slice(0, 10);
}

/**
 * The signing key a production request carried, as the server read it: algorithm,
 * SHA-256 fingerprint (to compare with the partner, e.g. over the phone) and, for a
 * certificate, whose it is, who signed it and until when it is valid.
 */
export function PartnerKeySummary({ info, now = new Date() }: { info: PartnerKeyInfo; now?: Date }) {
  const cert = info.certificate;
  const expired = cert ? new Date(cert.not_after) < now : false;
  return (
    <div className="mt-3 rounded-lg border border-hairline bg-surface-soft p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-medium text-subtle">Signing key</p>
        <Badge variant="info">{info.algorithm}</Badge>
        <Badge variant="neutral">{info.source === "certificate" ? "From certificate" : "Public key only"}</Badge>
        {cert?.self_signed ? <Badge variant="warning">Self-signed</Badge> : null}
        {expired ? <Badge variant="danger">Expired</Badge> : null}
      </div>
      <dl className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <dt className="text-xs font-medium text-subtle">SHA-256 fingerprint</dt>
          <dd className="mt-0.5 font-mono text-[0.7rem] break-all text-ink">{info.fingerprint_sha256}</dd>
        </div>
        {cert ? (
          <>
            <div>
              <dt className="text-xs font-medium text-subtle">Issued to</dt>
              <dd className="mt-0.5 break-words text-ink" title={cert.subject}>
                {cert.common_name ?? cert.subject}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-subtle">Issued by</dt>
              <dd className="mt-0.5 break-words text-ink">{cert.self_signed ? "Itself (self-signed)" : cert.issuer}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-subtle">Valid</dt>
              <dd className="mt-0.5 text-ink">
                {day(cert.not_before)} to {day(cert.not_after)}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-medium text-subtle">Serial number</dt>
              <dd className="mt-0.5 font-mono text-xs text-ink">{cert.serial_number}</dd>
            </div>
          </>
        ) : null}
      </dl>
    </div>
  );
}
