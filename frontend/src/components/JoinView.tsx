import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { joinReports } from "../api";
import { CloseIcon, FileIcon, MergeIcon, UploadIcon } from "./Icons";

type Notify = (message: string, kind?: "success" | "error") => void;

// Столько же принимает `/join`.
const MAX_FILES = 50;

const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} МБ`
    : `${(bytes / 1024).toFixed(1)} КБ`;

const plural = (count: number, one: string, few: string, many: string) => {
  const tail = count % 10;
  const hundred = count % 100;
  if (tail === 1 && hundred !== 11) return one;
  if (tail >= 2 && tail <= 4 && (hundred < 12 || hundred > 14)) return few;
  return many;
};

// Один и тот же файл легко выбрать дважды, обходя папки по очереди.
const fileKey = (file: File) => `${file.name}:${file.size}:${file.lastModified}`;

export function JoinView({ notify }: { notify: Notify }) {
  const [files, setFiles] = useState<File[]>([]);
  const [joining, setJoining] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const addFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    // Выбор не заменяет список, а дополняет: файлы обычно лежат по разным
    // папкам, и за один заход их не собрать.
    setFiles((current) => {
      const known = new Set(current.map(fileKey));
      const added = picked.filter((file) => !known.has(fileKey(file)));
      return [...current, ...added].slice(0, MAX_FILES);
    });
    // Сброс, иначе тот же файл повторно не выбрать после удаления из списка.
    event.target.value = "";
  };

  const removeFile = (key: string) => {
    setFiles((current) => current.filter((file) => fileKey(file) !== key));
  };

  const join = async (event: FormEvent) => {
    event.preventDefault();
    if (files.length < 2) return;
    setJoining(true);
    try {
      const result = await joinReports(files);
      notify(`Объединено файлов: ${result.files}. Строк в отчёте: ${result.rows}`);
    } catch (error) {
      notify(
        error instanceof Error ? error.message : "Объединение завершилось с ошибкой",
        "error",
      );
    } finally {
      setJoining(false);
    }
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Центр обработки</span>
          <h1>Объединить отчёты</h1>
          <p>Сложите несколько Excel-файлов в один общий.</p>
        </div>
      </div>

      <section className="join-grid">
        <article className="operation-card">
          <div className="operation-card__number">03</div>
          <div className="operation-card__icon operation-card__icon--light">
            <MergeIcon />
          </div>
          <span className="eyebrow">Join reports</span>
          <h2>Выбрать файлы</h2>
          <p>
            Колонки сопоставляются по названию, поэтому в одно объединение
            попадают и отчёты, снятые до появления новой колонки. Строки на
            повторы не проверяются — так быстрее.
          </p>

          <form onSubmit={join} className="operation-form">
            <input
              ref={fileInput}
              hidden
              multiple
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={addFiles}
            />
            <button
              className={`file-drop ${files.length ? "file-drop--selected" : ""}`}
              type="button"
              disabled={joining || files.length >= MAX_FILES}
              onClick={() => fileInput.current?.click()}
            >
              {files.length ? <FileIcon /> : <UploadIcon />}
              <span>
                <strong>
                  {files.length
                    ? `Выбрано файлов: ${files.length}`
                    : "Выберите Excel-файлы"}
                </strong>
                <small>
                  {files.length >= MAX_FILES
                    ? `Больше ${MAX_FILES} файлов за раз нельзя`
                    : files.length
                      ? "Можно выбрать ещё — список дополнится"
                      : `Формат .xlsx · от 2 до ${MAX_FILES} файлов`}
                </small>
              </span>
            </button>

            {files.length ? (
              <ul className="join-list">
                {files.map((file) => (
                  <li className="join-item" key={fileKey(file)}>
                    <FileIcon />
                    <span>
                      <strong>{file.name}</strong>
                      <small>{formatSize(file.size)}</small>
                    </span>
                    <button
                      className="icon-button"
                      type="button"
                      disabled={joining}
                      aria-label={`Убрать файл ${file.name}`}
                      onClick={() => removeFile(fileKey(file))}
                    >
                      <CloseIcon />
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}

            <button
              className="button button--primary button--wide"
              type="submit"
              disabled={joining || files.length < 2}
            >
              {joining ? <span className="spinner" /> : <MergeIcon />}
              {joining
                ? "Объединяем…"
                : files.length < 2
                  ? "Выберите хотя бы два файла"
                  : `Объединить ${files.length} ${plural(files.length, "файл", "файла", "файлов")} и скачать`}
            </button>
          </form>
        </article>
      </section>
    </>
  );
}
