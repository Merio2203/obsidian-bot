import React, { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";
const DEV_INIT_DATA = import.meta.env.VITE_DEV_INIT_DATA || "";

const TABS = [
  ["today", "Сегодня"],
  ["tasks", "Задачи"],
  ["projects", "Проекты"],
  ["diary", "Дневник"],
  ["resources", "Библиотека"],
  ["notes", "Входящие"],
  ["settings", "Настройки"],
];

function parseDiarySections(content) {
  if (!content) {
    return { mood: "😐", day: "", done: "", ideas: "", tomorrow: "" };
  }
  const getBlock = (title) => {
    const regex = new RegExp(`## ${title}\\n([\\s\\S]*?)(?=\\n## |$)`, "m");
    const match = content.match(regex);
    return match ? match[1].trim() : "";
  };
  const moodMatch = content.match(/^mood:\s*(.+)$/m);
  return {
    mood: moodMatch ? moodMatch[1].trim() : "😐",
    day: getBlock("🌅 Как прошёл день"),
    done: getBlock("✅ Что сделал"),
    ideas: getBlock("💭 Мысли и идеи"),
    tomorrow: getBlock("🎯 Планы на завтра"),
  };
}

export default function App() {
  const [tab, setTab] = useState("today");
  const [initData, setInitData] = useState(null);
  const [authOk, setAuthOk] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [dashboard, setDashboard] = useState("");
  const [projects, setProjects] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [notes, setNotes] = useState([]);
  const [resources, setResources] = useState([]);
  const [settings, setSettings] = useState(null);
  const [diary, setDiary] = useState({ mood: "😐", day: "", done: "", ideas: "", tomorrow: "" });

  const [projectForm, setProjectForm] = useState({ name: "", description: "", stack: "", repo_url: "" });
  const [taskForm, setTaskForm] = useState({ project_id: "", description: "", priority: "⚡ Средний", deadline: "" });
  const [noteForm, setNoteForm] = useState({ content: "", note_type: "inbox" });
  const [resourceForm, setResourceForm] = useState({ url: "" });

  useEffect(() => {
    let done = false;
    const startedAt = Date.now();

    const tryInit = () => {
      if (done) return;

      const tg = window.Telegram?.WebApp;
      if (tg) {
        tg.ready();
        tg.expand();
        const data = tg.initData || "";
        if (data) {
          done = true;
          setInitData(data);
          return;
        }
      }

      if (DEV_INIT_DATA) {
        done = true;
        setInitData(DEV_INIT_DATA);
        return;
      }

      if (Date.now() - startedAt > 10000) {
        done = true;
        setInitData("");
        setError(
          "Не удалось получить initData от Telegram. Открой приложение кнопкой из бота снова."
        );
      }
    };

    tryInit();
    const timer = setInterval(tryInit, 300);
    return () => {
      done = true;
      clearInterval(timer);
    };
  }, []);

  const headers = useMemo(() => {
    if (!initData) return { "Content-Type": "application/json" };
    return {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": initData,
    };
  }, [initData]);

  async function api(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { ...headers, ...(options.headers || {}) },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    return response.json();
  }

  async function bootstrap() {
    if (!initData) return;
    setBusy(true);
    setError("");
    try {
      await fetch(`${API_BASE}/auth/telegram/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ init_data: initData }),
      }).then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Auth failed");
        }
      });
      setAuthOk(true);
      await Promise.all([
        loadDashboard(),
        loadProjects(),
        loadTasks(),
        loadNotes(),
        loadResources(),
        loadSettings(),
        loadDiary(),
      ]);
    } catch (e) {
      setError(e.message || "Ошибка авторизации");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    bootstrap();
  }, [initData]);

  async function loadDashboard() {
    const data = await api("/today/dashboard");
    setDashboard(data.text || "");
  }

  async function loadProjects() {
    setProjects(await api("/projects"));
  }

  async function loadTasks() {
    setTasks(await api("/tasks?completed=false"));
  }

  async function loadNotes() {
    setNotes(await api("/notes"));
  }

  async function loadResources() {
    setResources(await api("/resources"));
  }

  async function loadSettings() {
    setSettings(await api("/settings"));
  }

  async function loadDiary() {
    const data = await api("/diary/today");
    if (data.exists) {
      setDiary(parseDiarySections(data.content || ""));
    }
  }

  async function submitProject(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/projects", {
        method: "POST",
        body: JSON.stringify({ ...projectForm, repo_url: projectForm.repo_url || null }),
      });
      setProjectForm({ name: "", description: "", stack: "", repo_url: "" });
      await loadProjects();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitTask(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/tasks", {
        method: "POST",
        body: JSON.stringify({
          project_id: taskForm.project_id ? Number(taskForm.project_id) : null,
          description: taskForm.description,
          priority: taskForm.priority,
          deadline: taskForm.deadline || null,
        }),
      });
      setTaskForm({ project_id: "", description: "", priority: "⚡ Средний", deadline: "" });
      await loadTasks();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleTask(task) {
    setBusy(true);
    try {
      await api(`/tasks/${task.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ completed: !task.completed }),
      });
      await loadTasks();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitNote(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/notes", { method: "POST", body: JSON.stringify(noteForm) });
      setNoteForm({ content: "", note_type: "inbox" });
      await loadNotes();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitResource(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/resources", { method: "POST", body: JSON.stringify(resourceForm) });
      setResourceForm({ url: "" });
      await loadResources();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitDiary(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/diary/today", {
        method: "PUT",
        body: JSON.stringify({
          mood: diary.mood,
          day: diary.day,
          done: diary.done,
          ideas: diary.ideas,
          tomorrow: diary.tomorrow,
        }),
      });
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function patchSettings(next) {
    setBusy(true);
    try {
      await api("/settings", { method: "PATCH", body: JSON.stringify(next) });
      await loadSettings();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function runSync() {
    setBusy(true);
    try {
      await api("/settings/sync", { method: "POST" });
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  if (initData === null) {
    return <div className="app"><p>Ожидание initData Telegram WebApp...</p></div>;
  }

  if (!initData) {
    return (
      <div className="app">
        <h1>Obsidian App</h1>
        {error && <div className="alert">{error}</div>}
        <p>Если открываешь не из Telegram, добавь `VITE_DEV_INIT_DATA` для локальной отладки.</p>
      </div>
    );
  }

  return (
    <div className="app">
      <h1>Obsidian App</h1>
      {error && <div className="alert">{error}</div>}
      {!authOk && <p>Проверка доступа...</p>}
      <div className="tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {tab === "today" && (
        <section>
          <button onClick={loadDashboard} disabled={busy}>Обновить</button>
          <pre>{dashboard}</pre>
        </section>
      )}

      {tab === "tasks" && (
        <section>
          <form onSubmit={submitTask}>
            <h3>Новая задача</h3>
            <select value={taskForm.project_id} onChange={(e) => setTaskForm({ ...taskForm, project_id: e.target.value })}>
              <option value="">Без проекта</option>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <textarea placeholder="Описание" value={taskForm.description} onChange={(e) => setTaskForm({ ...taskForm, description: e.target.value })} required />
            <select value={taskForm.priority} onChange={(e) => setTaskForm({ ...taskForm, priority: e.target.value })}>
              <option>🔥 Высокий</option>
              <option>⚡ Средний</option>
              <option>🌿 Низкий</option>
            </select>
            <input type="date" value={taskForm.deadline} onChange={(e) => setTaskForm({ ...taskForm, deadline: e.target.value })} />
            <button disabled={busy}>Создать</button>
          </form>
          <ul>
            {tasks.map((t) => (
              <li key={t.id}>
                <button onClick={() => toggleTask(t)}>{t.completed ? "↩" : "✅"}</button> {t.title}
              </li>
            ))}
          </ul>
        </section>
      )}

      {tab === "projects" && (
        <section>
          <form onSubmit={submitProject}>
            <h3>Новый проект</h3>
            <input placeholder="Название" value={projectForm.name} onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })} required />
            <textarea placeholder="Описание" value={projectForm.description} onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })} />
            <input placeholder="Стек через запятую" value={projectForm.stack} onChange={(e) => setProjectForm({ ...projectForm, stack: e.target.value })} />
            <input placeholder="Repo URL" value={projectForm.repo_url} onChange={(e) => setProjectForm({ ...projectForm, repo_url: e.target.value })} />
            <button disabled={busy}>Создать</button>
          </form>
          <ul>
            {projects.map((p) => <li key={p.id}>{p.status} {p.name}</li>)}
          </ul>
        </section>
      )}

      {tab === "diary" && (
        <section>
          <form onSubmit={submitDiary}>
            <h3>Дневник за сегодня</h3>
            <input value={diary.mood} onChange={(e) => setDiary({ ...diary, mood: e.target.value })} />
            <textarea placeholder="Как прошёл день" value={diary.day} onChange={(e) => setDiary({ ...diary, day: e.target.value })} />
            <textarea placeholder="Что сделал" value={diary.done} onChange={(e) => setDiary({ ...diary, done: e.target.value })} />
            <textarea placeholder="Мысли и идеи" value={diary.ideas} onChange={(e) => setDiary({ ...diary, ideas: e.target.value })} />
            <textarea placeholder="Планы на завтра" value={diary.tomorrow} onChange={(e) => setDiary({ ...diary, tomorrow: e.target.value })} />
            <button disabled={busy}>Сохранить</button>
          </form>
        </section>
      )}

      {tab === "resources" && (
        <section>
          <form onSubmit={submitResource}>
            <h3>Добавить ресурс</h3>
            <input placeholder="URL" value={resourceForm.url} onChange={(e) => setResourceForm({ url: e.target.value })} required />
            <button disabled={busy}>Сохранить</button>
          </form>
          <ul>
            {resources.map((r) => <li key={r.id}>{r.type}: {r.title}</li>)}
          </ul>
        </section>
      )}

      {tab === "notes" && (
        <section>
          <form onSubmit={submitNote}>
            <h3>Входящая заметка</h3>
            <textarea value={noteForm.content} onChange={(e) => setNoteForm({ ...noteForm, content: e.target.value })} required />
            <button disabled={busy}>Сохранить</button>
          </form>
          <ul>
            {notes.map((n) => <li key={n.id}>{n.title}</li>)}
          </ul>
        </section>
      )}

      {tab === "settings" && settings && (
        <section>
          <h3>Настройки</h3>
          <label>
            Timezone
            <input value={settings.timezone} onChange={(e) => setSettings({ ...settings, timezone: e.target.value })} />
          </label>
          <button onClick={() => patchSettings({ timezone: settings.timezone })} disabled={busy}>Сохранить timezone</button>
          <button onClick={() => patchSettings({ log_level: "INFO" })} disabled={busy}>INFO</button>
          <button onClick={() => patchSettings({ log_level: "WARNING" })} disabled={busy}>WARNING</button>
          <button onClick={() => patchSettings({ diary_reminder_enabled: !settings.diary_reminder_enabled })} disabled={busy}>
            Дневник: {settings.diary_reminder_enabled ? "ВКЛ" : "ВЫКЛ"}
          </button>
          <button onClick={() => patchSettings({ morning_digest_enabled: !settings.morning_digest_enabled })} disabled={busy}>
            Дайджест: {settings.morning_digest_enabled ? "ВКЛ" : "ВЫКЛ"}
          </button>
          <button onClick={runSync} disabled={busy}>Синхронизировать</button>
        </section>
      )}
    </div>
  );
}
