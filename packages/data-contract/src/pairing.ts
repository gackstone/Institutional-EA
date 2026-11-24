import { z } from "zod";

export const PairingQrPayloadSchema = z.object({
  v: z.literal(1),
  relayUrl: z.string().url(),
  sessionId: z.string().uuid(),
  publicKey: z.string().min(16),
  expiresAt: z.number().int().positive(),
});

export type PairingQrPayload = z.infer<typeof PairingQrPayloadSchema>;

export const PairingClaimRequestSchema = z.object({
  sessionId: z.string().uuid(),
  deviceFingerprint: z.string().min(8),
  deviceName: z.string().min(1).max(64),
  platform: z.enum(["ios", "android", "web"]),
});

export type PairingClaimRequest = z.infer<typeof PairingClaimRequestSchema>;

export const DeviceTokenPayloadSchema = z.object({
  sub: z.string().min(1), // device ID
  accountMasked: z.string().min(1),
  scopes: z.array(z.string()).refine((scopes) => scopes.every((s) => s.startsWith("telemetry:read")), {
    message: "Strict security violation: device token contains non-read-only scopes",
  }),
  iat: z.number().int().positive(),
  exp: z.number().int().positive(),
});

export type DeviceTokenPayload = z.infer<typeof DeviceTokenPayloadSchema>;

export const RevokeDeviceRequestSchema = z.object({
  deviceId: z.string().min(1),
});

export type RevokeDeviceRequest = z.infer<typeof RevokeDeviceRequestSchema>;
