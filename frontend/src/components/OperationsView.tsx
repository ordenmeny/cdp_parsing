import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { defineSellers, runScrolling } from "../api";
import { FileIcon, PlayIcon, UploadIcon } from "./Icons";

type Notify = (message: string, kind?: "success" | "error") => void;

export function OperationsView({ notify }: { notify: Notify }) {
  const [query, setQuery] = useState("");
  const [parsing, setParsing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [limit, setLimit] = useState(4);
  const [defining, setDefining] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const parse = async (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setParsing(true);
    try {
      const count = await runScrolling(query.trim());
      notify(`Парсинг завершён. Собрано карточек: ${count}`);
    } catch (error) {
      notify(error instanceof Error ? error.message : "Парсинг завершился с ошибкой", "error");
    } finally {
      setParsing(false);
    }
  };

  const define = async (event: FormEvent) => {
    event.preventDefault();
    setDefining(true);
    try {
      const result = await defineSellers(limit, file);
      if (file) {
        notify(`Файл «${file.name}» обработан и загружен`);
      } else if (result) {
        notify(
          `Проверено: ${result.processed}. Корректных: ${result.confirmed}, некорректных: ${result.incorrect}`,
        );
      }
    } catch (error) {
      notify(error instanceof Error ? error.message : "Проверка завершилась с ошибкой", "error");
    } finally {
      setDefining(false);
    }
  };

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Центр обработки</span>
          <h1>Запуск задач</h1>
          <p>Собирайте выдачу и подтверждайте продавцов в одном месте.</p>
        </div>
      </div>

      <section className="operations-grid">
        <article className="operation-card operation-card--dark">
          <div className="operation-card__number">01</div>
          <div className="operation-card__icon"><PlayIcon /></div>
          <span className="eyebrow">Scrolling parser</span>
          <h2>Собрать товары</h2>

          <form onSubmit={parse} className="operation-form">
            <label className="field field--on-dark">
              <span>Поисковый запрос</span>
              <div className="command-input">
                <input
                  required
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="например, makita"
                />
              </div>
            </label>
            <button className="button button--accent button--wide" type="submit" disabled={parsing}>
              {parsing ? <span className="spinner spinner--dark" /> : <PlayIcon />}
              {parsing ? "Идёт сбор…" : "Запустить и скачать Excel"}
            </button>
          </form>
          {parsing ? (
            <div className="operation-progress">
              <span className="operation-progress__line" />
              Не закрывайте вкладку Megamarket в браузере
            </div>
          ) : null}
        </article>

        <article className="operation-card">
          <div className="operation-card__number">02</div>
          <div className="operation-card__icon operation-card__icon--light"><UploadIcon /></div>
          <span className="eyebrow">Define sellers</span>
          <h2>Проверить продавцов</h2>
          <p>
            Добавьте новых продавцов из отчёта и проверьте ссылки со статусом
            «На проверке».
          </p>

          <form onSubmit={define} className="operation-form">
            <input
              ref={fileInput}
              hidden
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={selectFile}
            />
            <button
              className={`file-drop ${file ? "file-drop--selected" : ""}`}
              type="button"
              onClick={() => fileInput.current?.click()}
            >
              {file ? <FileIcon /> : <UploadIcon />}
              <span>
                <strong>{file ? file.name : "Выберите Excel-файл"}</strong>
                <small>{file ? `${(file.size / 1024).toFixed(1)} КБ` : "Файл необязателен · формат .xlsx"}</small>
              </span>
            </button>

            <label className="field">
              <span>Сколько продавцов проверить</span>
              <input
                type="number"
                min="1"
                required
                value={limit}
                onChange={(event) => setLimit(Math.max(1, Number(event.target.value)))}
              />
            </label>
            <button className="button button--primary button--wide" type="submit" disabled={defining}>
              {defining ? <span className="spinner" /> : <UploadIcon />}
              {defining ? "Идёт проверка…" : file ? "Проверить и скачать файл" : "Проверить продавцов"}
            </button>
          </form>
        </article>
      </section>

    </>
  );
}
