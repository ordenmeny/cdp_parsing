import { useState, type FormEvent } from "react";
import { setSellers } from "../api";
import type { Seller, SellerStatus, SellerUpdate } from "../types";
import { CloseIcon } from "./Icons";

interface SellerEditorProps {
  seller: Seller;
  onClose: () => void;
  onSaved: (seller: Seller) => void;
  onError: (message: string) => void;
}

export function SellerEditor({
  seller,
  onClose,
  onSaved,
  onError,
}: SellerEditorProps) {
  const [form, setForm] = useState({
    status: seller.status,
    link_to_seller: seller.link_to_seller,
    link_to_card: seller.link_to_card,
    email: seller.email,
    phone: seller.phone,
    inn: seller.inn,
    ogrn: seller.ogrn,
    official_name: seller.official_name,
  });
  const [saving, setSaving] = useState(false);

  const update = (field: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    const payload: SellerUpdate = {
      seller_id: seller.seller_id,
      ...form,
      status: form.status as SellerStatus,
    };
    try {
      const [updated] = await setSellers(payload);
      onSaved(updated);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Не удалось сохранить продавца");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="editor-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="editor__header">
          <div>
            <span className="eyebrow">Редактирование продавца</span>
            <h2 id="editor-title">{seller.name}</h2>
            <p>ID {seller.seller_id}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Закрыть">
            <CloseIcon />
          </button>
        </header>

        <form onSubmit={submit} className="editor__form">
          <label className="field field--full">
            <span>Статус</span>
            <select
              value={form.status}
              onChange={(event) => update("status", event.target.value)}
            >
              <option value="correct">Корректный</option>
              <option value="unconfirmed">На проверке</option>
              <option value="incorrect">Некорректный</option>
            </select>
          </label>

          <label className="field field--full">
            <span>Ссылка на продавца</span>
            <input
              required
              type="url"
              value={form.link_to_seller}
              onChange={(event) => update("link_to_seller", event.target.value)}
            />
          </label>

          <label className="field field--full">
            <span>Ссылка на карточку</span>
            <input
              required
              type="url"
              value={form.link_to_card}
              onChange={(event) => update("link_to_card", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={form.email}
              onChange={(event) => update("email", event.target.value)}
            />
          </label>
          <label className="field">
            <span>Телефон</span>
            <input value={form.phone} onChange={(event) => update("phone", event.target.value)} />
          </label>
          <label className="field">
            <span>ИНН</span>
            <input value={form.inn} onChange={(event) => update("inn", event.target.value)} />
          </label>
          <label className="field">
            <span>ОГРН</span>
            <input value={form.ogrn} onChange={(event) => update("ogrn", event.target.value)} />
          </label>
          <label className="field field--full">
            <span>Официальное название</span>
            <input
              value={form.official_name}
              onChange={(event) => update("official_name", event.target.value)}
            />
          </label>
          <footer className="editor__actions">
            <button className="button button--ghost" type="button" onClick={onClose}>
              Отмена
            </button>
            <button className="button button--primary" type="submit" disabled={saving}>
              {saving ? <span className="spinner" /> : null}
              {saving ? "Сохраняем" : "Сохранить"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
