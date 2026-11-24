import { z } from "zod";

export const KpiSummarySchema = z.object({
  balance: z.number().nonnegative(),
  equity: z.number(),
  todayPnl: z.number(),
  totalProfit: z.number(),
  winRate: z.number().min(0).max(100),
  todayTradesCount: z.number().int().nonnegative(),
  totalDealsCount: z.number().int().nonnegative(),
  calculatedAt: z.number().int().positive(),
});

export type KpiSummary = z.infer<typeof KpiSummarySchema>;
