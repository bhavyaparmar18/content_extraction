import { z } from 'zod';

const noControlCharacters = /^[^\u0000-\u001F\u007F]*$/u;

export const signupSchema = z
  .object({
    firstName: z
      .string()
      .trim()
      .min(1, 'First name is required.')
      .max(100, 'First name must not exceed 100 characters.')
      .regex(noControlCharacters, 'First name contains unsupported characters.'),

    lastName: z
      .string()
      .trim()
      .min(1, 'Last name is required.')
      .max(100, 'Last name must not exceed 100 characters.')
      .regex(noControlCharacters, 'Last name contains unsupported characters.'),

    biEmail: z
      .string()
      .trim()
      .email('Enter a valid BI email address.')
      .max(320, 'Email must not exceed 320 characters.'),

    password: z
      .string()
      .min(12, 'Password must contain at least 12 characters.')
      .max(128, 'Password must not exceed 128 characters.'),

    confirmPassword: z.string().min(1, 'Confirm your password.'),

    secretQuestionId: z
      .string()
      .min(1, 'Select a valid secret question.')
      .uuid('Select a valid secret question.'),

    secretAnswer: z
      .string()
      .trim()
      .min(2, 'Secret answer must contain at least 2 characters.')
      .max(255, 'Secret answer must not exceed 255 characters.'),
  })
  .superRefine((values, context) => {
    if (values.password !== values.confirmPassword) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['confirmPassword'],
        message: 'Password and confirm password must match.',
      });
    }

    if (values.biEmail && values.password.toLocaleLowerCase() === values.biEmail.trim().toLocaleLowerCase()) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['password'],
        message: 'Password must not be the same as your email address.',
      });
    }
  });

export type SignupSchemaType = z.infer<typeof signupSchema>;
