import type {
  DefineSellersResult,
  Seller,
  SellerStatus,
  SellerUpdate,
} from "./types";

// Интерфейс раздаёт то же приложение, что и API, поэтому по умолчанию адрес
// пустой — запросы уходят на текущий источник. Переменная нужна только для
// `npm run dev` и в сборке может отсутствовать.
const configuredBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").trim();
const baseUrl = configuredBaseUrl.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  let message = `Ошибка API (${response.status})`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      message = body.detail;
    } else if (body.detail) {
      message = JSON.stringify(body.detail);
    }
  } catch {
    const text = await response.text().catch(() => "");
    if (text) message = text;
  }
  return new ApiError(message, response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, init);
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as T;
}

export async function getSellers(status?: SellerStatus): Promise<Seller[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<Seller[]>(`/get_sellers${query}`);
}

export async function setSellers(
  updates: SellerUpdate | SellerUpdate[],
): Promise<Seller[]> {
  return request<Seller[]>("/set_sellers", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

function filenameFromResponse(response: Response, fallback: string): string {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (utf8) return decodeURIComponent(utf8);
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  return plain ?? fallback;
}

async function downloadResponse(response: Response, fallback: string) {
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filenameFromResponse(response, fallback);
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// Все запросы уходят одним вызовом: сервер обходит их подряд в одной вкладке
// и отдаёт единственный файл со всей собранной выдачей.
export async function runScrolling(
  queries: string[],
): Promise<{ cards: number; parsed: number; total: number }> {
  const response = await fetch(`${baseUrl}/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      commands: queries.map((query) => `scrolling||${query}`),
    }),
  });
  if (!response.ok) throw await errorFromResponse(response);
  const result = {
    cards: Number(response.headers.get("X-Cards-Collected") ?? 0),
    parsed: Number(response.headers.get("X-Queries-Parsed") ?? queries.length),
    total: Number(response.headers.get("X-Queries-Total") ?? queries.length),
  };
  await downloadResponse(response, "megamarket-result.xlsx");
  return result;
}

export async function defineSellers(
  limit: number,
  file: File | null,
): Promise<DefineSellersResult | null> {
  const options: RequestInit = { method: "POST" };
  if (file) {
    const form = new FormData();
    form.append("file", file);
    options.body = form;
  }

  const response = await fetch(
    `${baseUrl}/define_sellers?limit=${encodeURIComponent(limit)}`,
    options,
  );
  if (!response.ok) throw await errorFromResponse(response);

  if (file) {
    await downloadResponse(response, file.name);
    return null;
  }
  return (await response.json()) as DefineSellersResult;
}

export async function defineSelectedSellers(
  sellerIds: string[],
): Promise<DefineSellersResult> {
  return request<DefineSellersResult>("/define_sellers/selected", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seller_ids: sellerIds }),
  });
}

export async function joinReports(
  files: File[],
): Promise<{ files: number; rows: number }> {
  const form = new FormData();
  for (const file of files) form.append("files", file);

  const response = await fetch(`${baseUrl}/join`, { method: "POST", body: form });
  if (!response.ok) throw await errorFromResponse(response);

  const joined = {
    files: Number(response.headers.get("X-Files-Joined") ?? files.length),
    rows: Number(response.headers.get("X-Rows-Joined") ?? 0),
  };
  await downloadResponse(response, "megamarket-joined.xlsx");
  return joined;
}
