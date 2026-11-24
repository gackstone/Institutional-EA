import { z } from "zod";
import { AccountStateSchema } from "./account.ts";
import { PositionSchema } from "./positions.ts";
import { TradeDealSchema } from "./trades.ts";
import { SmcZoneSchema } from "./smcZones.ts";
import { CandleSchema } from "./candles.ts";
import { KpiSummarySchema } from "./kpi.ts";

export const TelemetrySnapshotSchema = z.object({
  version: z.literal(1),
  timestamp: z.number().int().positive(),
  account: AccountStateSchema,
  positions: z.array(PositionSchema),
  recentDeals: z.array(TradeDealSchema),
  kpis: KpiSummarySchema,
  zones: z.record(z.string(), z.array(SmcZoneSchema)), // symbol -> zones
  recentCandles: z.record(z.string(), z.array(CandleSchema)).optional(), // symbol -> candles
});

export type TelemetrySnapshot = z.infer<typeof TelemetrySnapshotSchema>;

export const TelemetryDeltaSchema = z.object({
  version: z.literal(1),
  timestamp: z.number().int().positive(),
  account: AccountStateSchema.partial().optional(),
  positions: z.array(PositionSchema).optional(),
  closedDeals: z.array(TradeDealSchema).optional(),
  kpis: KpiSummarySchema.partial().optional(),
  newZones: z.array(SmcZoneSchema).optional(),
  mitigatedZoneIds: z.array(z.string()).optional(),
});

export type TelemetryDelta = z.infer<typeof TelemetryDeltaSchema>;

export const WsTelemetryMessageSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("SNAPSHOT"),
    data: TelemetrySnapshotSchema,
  }),
  z.object({
    type: z.literal("DELTA"),
    data: TelemetryDeltaSchema,
  }),
  z.object({
    type: z.literal("PING"),
    timestamp: z.number(),
  }),
  z.object({
    type: z.literal("PONG"),
    timestamp: z.number(),
  }),
]);

export type WsTelemetryMessage = z.infer<typeof WsTelemetryMessageSchema>;
