import { z } from "zod";

export const SmcZoneTypeSchema = z.enum(["FVG", "OB", "IFVG"]);
export type SmcZoneType = z.infer<typeof SmcZoneTypeSchema>;

export const SmcZoneStatusSchema = z.enum(["UNMITIGATED", "MITIGATED"]);
export type SmcZoneStatus = z.infer<typeof SmcZoneStatusSchema>;

export const SmcZoneDirectionSchema = z.enum(["BULL", "BEAR"]);
export type SmcZoneDirection = z.infer<typeof SmcZoneDirectionSchema>;

export const SmcZoneSchema = z.object({
  id: z.string().min(1),
  type: SmcZoneTypeSchema,
  direction: SmcZoneDirectionSchema,
  timeframe: z.string().min(1),
  symbol: z.string().min(1),
  top: z.number().positive(),
  bottom: z.number().positive(),
  startTime: z.number().int().positive(),
  endTime: z.number().int().positive().nullable().default(null),
  status: SmcZoneStatusSchema.default("UNMITIGATED"),
  label: z.enum(["FVG", "OB", "IFVG"]),
});

export type SmcZone = z.infer<typeof SmcZoneSchema>;
