import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { defineSellers, runScrolling } from "../api";
import { CloseIcon, FileIcon, PlayIcon, PlusIcon, UploadIcon } from "./Icons";

type Notify = (message: string, kind?: "success" | "error") => void;

// Столько же принимает `/parse`: предупредить о пределе лучше здесь, чем
// показывать пользователю отказ сервера.
const MAX_QUERIES = 20;

type QueryField = { id: number; value: string };

export function OperationsView({ notify }: { notify: Notify }) {
  const [queries, setQueries] = useState<QueryField[]>([{ id: 0, value: "" }]);
  const nextQueryId = useRef(1);
  const [parsing, setParsing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [limit, setLimit] = useState(4);
  const [defining, setDefining] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const addQuery = () => {
    setQueries((current) =>
      current.length >= MAX_QUERIES
        ? current
        : [...current, { id: nextQueryId.current++, value: "" }],
    );
  };

  // Последнее поле не убираем: без него собирать было бы нечего.
  const removeQuery = (id: number) => {
    setQueries((current) =>
      current.length > 1 ? current.filter((field) => field.id !== id) : current,
    );
  };

  const changeQuery = (id: number, value: string) => {
    setQueries((current) =>
      current.map((field) => (field.id === id ? { ...field, value } : field)),
    );
  };

  const parse = async (event: FormEvent) => {
    event.preventDefault();
    // Пустые поля пользователь мог добавить и передумать — они просто
    // выпадают из запроса, а не мешают запуску.
    const values = queries
      .map((field) => field.value.trim())
      .filter((value) => value.length > 0);
    if (!values.length) return;
    setParsing(true);
    try {
      const count = await runScrolling(values);
      notify(
        values.length > 1
          ? `Парсинг завершён. Запросов: ${values.length}, собрано карточек: ${count}`
          : `Парсинг завершён. Собрано карточек: ${count}`,
      );
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
          <p>
            Запросы обходятся по очереди, а выдача всех них приходит одним
            Excel-файлом с колонкой «Запрос».
          </p>

          <form onSubmit={parse} className="operation-form">
            <div className="field field--on-dark">
              <span>
                {queries.length > 1
                  ? `Поисковые запросы · ${queries.length}`
                  : "Поисковый запрос"}
              </span>
              <div className="query-list">
                {queries.map((field, index) => (
                  <div className="query-row" key={field.id}>
                    <div className="command-input">
                      <input
                        required={index === 0}
                        value={field.value}
                        aria-label={`Поисковый запрос ${index + 1}`}
                        onChange={(event) => changeQuery(field.id, event.target.value)}
                        placeholder={index === 0 ? "например, makita" : "например, iphone 17"}
                      />
                    </div>
                    {queries.length > 1 ? (
                      <button
                        className="icon-button icon-button--on-dark"
                        type="button"
                        disabled={parsing}
                        aria-label={`Убрать запрос ${index + 1}`}
                        onClick={() => removeQuery(field.id)}
                      >
                        <CloseIcon />
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
            <button
              className="button button--ghost button--small button--on-dark"
              type="button"
              disabled={parsing || queries.length >= MAX_QUERIES}
              onClick={addQuery}
            >
              <PlusIcon />
              {queries.length >= MAX_QUERIES
                ? `Больше ${MAX_QUERIES} запросов за раз нельзя`
                : "Добавить запрос"}
            </button>
            <button className="button button--accent button--wide" type="submit" disabled={parsing}>
              {parsing ? <span className="spinner spinner--dark" /> : <PlayIcon />}
              {parsing
                ? "Идёт сбор…"
                : queries.length > 1
                  ? "Запустить и скачать один Excel"
                  : "Запустить и скачать Excel"}
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
            «Ещё не проверен».
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
