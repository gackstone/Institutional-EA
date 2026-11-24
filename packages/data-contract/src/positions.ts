import { z } from "zod";

export const PositionTypeSchema = z.enum(["BUY", "SELL"]);
export type PositionType = z.infer<typeof PositionTypeSchema>;

export const PositionSchema = z.object({
  ticket: z.number().int().positive(),
  symbol: z.string().min(1),
  type: PositionTypeSchema,
  volume: z.number().positive(),
  openPrice: z.number().positive(),
  currentPrice: z.number().positive(),
  sl: z.number().positive().nullable().default(null),
  tp: z.number().positive().nullable().default(null),
  profit: z.number(),
  swap: z.number().default(0),
  openTime: z.number().int().positive(),
  comment: z.string().optional().default(""),
});

export type Position = z.infer<typeof PositionSchema>;
