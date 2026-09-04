import type { SellerStatus } from "../types";

const labels: Record<SellerStatus, string> = {
  correct: "Корректный",
  unconfirmed: "Ещё не проверен",
  incorrect: "Некорректный",
};

export function StatusBadge({ status }: { status: SellerStatus }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <span className="status-badge__dot" />
      {labels[status]}
    </span>
  );
}

export { labels as statusLabels };
