import { z } from "zod";
import { PositionTypeSchema } from "./positions.ts";

export const TradeDealSchema = z.object({
  deal: z.number().int().positive(),
  order: z.number().int().positive(),
  time: z.number().int().positive(),
  symbol: z.string().min(1),
  type: PositionTypeSchema,
  volume: z.number().positive(),
  price: z.number().positive(),
  profit: z.number(),
  commission: z.number().default(0),
  swap: z.number().default(0),
  comment: z.string().optional().default(""),
});

export type TradeDeal = z.infer<typeof TradeDealSchema>;
