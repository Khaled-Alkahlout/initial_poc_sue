import { ApiError, errorMessage } from "./client";

/** Handle data-loading failures before rendering JSX; render failures use error.tsx. */
export async function loadPage<T>(
  loader: () => Promise<T>,
): Promise<
  { ok: true; data: T } | { ok: false; message: string; status: number }
> {
  try {
    return { ok: true, data: await loader() };
  } catch (error) {
    return {
      ok: false,
      message: errorMessage(error),
      status: error instanceof ApiError ? error.status : 500,
    };
  }
}
