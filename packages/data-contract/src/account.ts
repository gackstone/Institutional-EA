import { z } from "zod";

export const AccountStateSchema = z.object({
  balance: z.number().nonnegative(),
  equity: z.number(),
  margin: z.number().default(0),
  freeMargin: z.number().default(0),
  currency: z.string().default("USD"),
  leverage: z.number().positive().default(100),
  serverTime: z.number().int().positive(),
  accountNumber: z.string().min(1),
  syncedAt: z.string().datetime(),
  isLive: z.boolean().default(false),
});

export type AccountState = z.infer<typeof AccountStateSchema>;
