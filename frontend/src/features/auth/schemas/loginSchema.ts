import { z } from 'zod';

export const loginSchema = z.object({
  biEmail: z
    .string()
    .min(1, 'BI Email is required')
    .max(320, 'Email must not exceed 320 characters')
    .email('Please enter a valid company email address'),
  password: z
    .string()
    .min(1, 'Password is required')
    .max(128, 'Password must not exceed 128 characters'),
  rememberMe: z.boolean(),
});

export type LoginSchemaType = z.infer<typeof loginSchema>;
