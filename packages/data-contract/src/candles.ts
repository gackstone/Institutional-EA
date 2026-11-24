import { z } from "zod";

export const CandleSchema = z.object({
  time: z.number().int().positive(),
  open: z.number().positive(),
  high: z.number().positive(),
  low: z.number().positive(),
  close: z.number().positive(),
  volume: z.number().nonnegative().default(0),
});

export type Candle = z.infer<typeof CandleSchema>;
