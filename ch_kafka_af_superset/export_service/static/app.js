(() => {
  const state = {
    step: 1,
    dashboards: [],
    dashboard: null,
    filtersMeta: [],
    filterValues: {},
    exportId: null,
    preview: null,
    busy: false,
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toast._t);
    toast._t = setTimeout(() => {
      el.hidden = true;
    }, 3200);
  }

  function yearStart() {
    const d = new Date();
    return `${d.getFullYear()}-01-01`;
  }

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function monthStart() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
  }

  function daysAgo(n) {
    const d = new Date();
    d.setDate(d.getDate() - n);
    return d.toISOString().slice(0, 10);
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let data = null;
    const text = await res.text();
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { detail: text };
    }
    if (!res.ok) {
      const detail = data?.detail;
      let msg;
      if (typeof detail === "string") msg = detail;
      else if (detail && typeof detail === "object" && detail.message) msg = detail.message;
      else msg = JSON.stringify(detail || data);
      const err = new Error(msg || `Ошибка ${res.status}`);
      err.status = res.status;
      err.payload = detail;
      throw err;
    }
    return data;
  }

  function setTab(name) {
    $$(".tab").forEach((t) => t.classList.toggle("is-active", t.dataset.tab === name));
    $("#view-export").hidden = name !== "export";
    $("#view-connect").hidden = name !== "connect";
    const help = $("#top-help");
    if (name === "connect") {
      help.textContent = "Подключите дашборд Superset один раз — потом выгружайте данные без лимита 100 000 строк";
    } else {
      help.textContent = "Выберите отчёт → укажите фильтры → проверьте таблицу → скачайте файл";
    }
  }

  function setStep(n) {
    state.step = n;
    $$(".panel").forEach((p) => {
      const id = Number(p.id.replace("step-", ""));
      p.hidden = id !== n;
    });
    $$(".step").forEach((btn) => {
      const s = Number(btn.dataset.step);
      btn.classList.toggle("is-active", s === n);
      btn.classList.toggle("is-done", s < n);
      if (s === 1) btn.disabled = false;
      if (s === 2) btn.disabled = !state.dashboard;
      if (s === 3) btn.disabled = !state.dashboard;
      if (s === 4) btn.disabled = !state.dashboard || !state.exportId;
    });
    if (n === 2) renderSelectedBanners();
    if (n === 3) {
      renderSelectedBanners();
      renderExports();
    }
    if (n === 4) renderSummary();
  }

  function renderSelectedBanners() {
    const title = state.dashboard?.title || "—";
    ["selected-banner-2", "selected-banner-3"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = `Отчёт: ${title}`;
    });
  }

  function renderDashboards() {
    const root = $("#dashboard-grid");
    if (!state.dashboards.length) {
      root.innerHTML = `<p class="ms-empty">Нет подключённых отчётов. Обратитесь к администратору.</p>`;
      return;
    }
    root.innerHTML = state.dashboards
      .map(
        (d) => `
      <button type="button" class="dash-card ${state.dashboard?.id === d.id ? "is-selected" : ""}" data-id="${d.id}" role="option" aria-selected="${state.dashboard?.id === d.id}">
        <h3>${escapeHtml(d.title)}</h3>
        <p>${d.filter_count || 0} фильтров · ${d.exports?.length || 0} вариантов файла</p>
      </button>`
      )
      .join("");

    root.querySelectorAll(".dash-card").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const dash = state.dashboards.find((x) => x.id === btn.dataset.id);
        await selectDashboard(dash);
      });
    });
  }

  async function selectDashboard(dash) {
    state.dashboard = dash;
    state.exportId = null;
    state.preview = null;
    state.filterValues = {};
    renderDashboards();
    $("#filters-root").innerHTML = `<p class="ms-empty">Загрузка фильтров…</p>`;
    setStep(2);
    try {
      const data = await api(`/api/dashboards/${encodeURIComponent(dash.id)}/filters`);
      state.filtersMeta = data.filters || [];
      initFilterDefaults();
      renderFilters();
      // default export: prefer raw
      const raw = dash.exports?.find((e) => e.id === "raw");
      state.exportId = raw?.id || dash.exports?.[0]?.id || null;
    } catch (err) {
      $("#filters-root").innerHTML = `<p class="error">${escapeHtml(err.message)}</p>`;
    }
  }

  function initFilterDefaults() {
    for (const f of state.filtersMeta) {
      if (f.type === "date_range") {
        if (f.default === "relative:current_year" || !f.default) {
          state.filterValues[f.id] = { from: yearStart(), to: today() };
        } else if (typeof f.default === "object") {
          state.filterValues[f.id] = { ...f.default };
        } else {
          state.filterValues[f.id] = { from: yearStart(), to: today() };
        }
      } else if (f.type === "multi_select") {
        state.filterValues[f.id] = Array.isArray(f.default) ? [...f.default] : [];
      } else {
        state.filterValues[f.id] = f.default ?? "";
      }
    }
  }

  function renderFilters() {
    const root = $("#filters-root");
    if (!state.filtersMeta.length) {
      root.innerHTML = `<p class="ms-empty">У этого отчёта нет настраиваемых фильтров — можно сразу выбрать файл.</p>`;
      return;
    }
    root.innerHTML = state.filtersMeta.map((f) => filterHtml(f)).join("");
    bindFilterEvents(root);
  }

  function filterHtml(f) {
    if (f.type === "date_range") {
      const v = state.filterValues[f.id] || {};
      return `
        <div class="filter-card" data-filter="${f.id}">
          <label class="title">${escapeHtml(f.label)}</label>
          <div class="filter-row">
            <input type="date" data-bound="from" value="${v.from || ""}" aria-label="Дата с" />
            <input type="date" data-bound="to" value="${v.to || ""}" aria-label="Дата по" />
          </div>
          <div class="quick-dates">
            <button type="button" class="chip" data-quick="year">Текущий год</button>
            <button type="button" class="chip" data-quick="month">Текущий месяц</button>
            <button type="button" class="chip" data-quick="30">Последние 30 дней</button>
            <button type="button" class="chip" data-quick="clear">Сбросить</button>
          </div>
        </div>`;
    }
    if (f.type === "multi_select") {
      const selected = state.filterValues[f.id] || [];
      const lazy = !!(f.lazy || f.values_from?.lazy);
      const summary = selected.length
        ? `<strong>Выбрано: ${selected.length}</strong>`
        : `<span>Не выбрано — значит без ограничения</span>`;
      const selectedChips = selected.length
        ? `<div class="ms-selected">${selected
            .map(
              (val) =>
                `<button type="button" class="chip is-on" data-unselect="${escapeAttr(String(val))}" title="Убрать">× ${escapeHtml(String(val))}</button>`
            )
            .join("")}</div>`
        : "";
      const placeholder = lazy
        ? "Начните вводить название (мин. 2 буквы)…"
        : "Поиск…";
      const optionsHtml = lazy
        ? `<div class="ms-empty" data-lazy-hint>Введите минимум 2 символа для поиска по справочнику</div>`
        : (f.values || [])
            .map(
              (val) => `
                  <label class="ms-option" data-text="${escapeAttr(String(val).toLowerCase())}">
                    <input type="checkbox" value="${escapeAttr(String(val))}" ${selected.includes(val) ? "checked" : ""} />
                    <span>${escapeHtml(String(val))}</span>
                  </label>`
            )
            .join("") || `<div class="ms-empty">Список значений недоступен</div>`;
      return `
        <div class="filter-card" data-filter="${f.id}" data-lazy="${lazy ? "1" : "0"}">
          <label class="title">${escapeHtml(f.label)}</label>
          ${selectedChips}
          <div class="ms">
            <button type="button" class="ms-control" data-toggle-ms>
              ${summary}
              <span>▼</span>
            </button>
            <div class="ms-panel" hidden>
              <input class="ms-search" type="search" placeholder="${placeholder}" />
              <div class="ms-options">${optionsHtml}</div>
              <div class="ms-actions">
                <button type="button" class="btn btn-ghost" data-ms-clear>Очистить</button>
                <button type="button" class="btn btn-secondary" data-ms-close>Готово</button>
              </div>
            </div>
          </div>
          ${f.values_error ? `<p class="error" style="margin-top:.6rem">Не удалось загрузить список: ${escapeHtml(f.values_error)}</p>` : ""}
        </div>`;
    }
    return `
      <div class="filter-card" data-filter="${f.id}">
        <label class="title">${escapeHtml(f.label)}</label>
        <input type="text" style="width:100%;padding:.6rem .75rem;border:1px solid var(--line-strong);border-radius:8px"
          value="${escapeAttr(state.filterValues[f.id] || "")}" data-text-input />
      </div>`;
  }

  function bindFilterEvents(root) {
    root.querySelectorAll(".filter-card").forEach((card) => {
      const id = card.dataset.filter;
      const meta = state.filtersMeta.find((f) => f.id === id);

      card.querySelectorAll('input[type="date"]').forEach((inp) => {
        inp.addEventListener("change", () => {
          const cur = state.filterValues[id] || {};
          cur[inp.dataset.bound] = inp.value;
          state.filterValues[id] = cur;
        });
      });

      card.querySelectorAll("[data-quick]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const q = btn.dataset.quick;
          let next = { from: "", to: "" };
          if (q === "year") next = { from: yearStart(), to: today() };
          if (q === "month") next = { from: monthStart(), to: today() };
          if (q === "30") next = { from: daysAgo(30), to: today() };
          if (q === "clear") next = { from: "", to: "" };
          state.filterValues[id] = next;
          card.querySelector('[data-bound="from"]').value = next.from;
          card.querySelector('[data-bound="to"]').value = next.to;
        });
      });

      const toggle = card.querySelector("[data-toggle-ms]");
      const panel = card.querySelector(".ms-panel");
      if (toggle && panel) {
        const isLazy = card.dataset.lazy === "1";
        toggle.addEventListener("click", () => {
          panel.hidden = !panel.hidden;
          if (!panel.hidden && isLazy) {
            card.querySelector(".ms-search")?.focus();
          }
        });
        card.querySelector("[data-ms-close]")?.addEventListener("click", () => {
          panel.hidden = true;
          renderFilters();
        });
        card.querySelector("[data-ms-clear]")?.addEventListener("click", () => {
          state.filterValues[id] = [];
          renderFilters();
          const again = $(`.filter-card[data-filter="${id}"] .ms-panel`);
          if (again) again.hidden = false;
        });
        card.querySelectorAll("[data-unselect]").forEach((chip) => {
          chip.addEventListener("click", () => {
            const val = chip.dataset.unselect;
            state.filterValues[id] = (state.filterValues[id] || []).filter((x) => x !== val);
            renderFilters();
          });
        });

        const searchInput = card.querySelector(".ms-search");
        if (isLazy) {
          let timer = null;
          searchInput?.addEventListener("input", () => {
            clearTimeout(timer);
            timer = setTimeout(() => lazySearch(card, id, searchInput.value), 280);
          });
        } else {
          searchInput?.addEventListener("input", (e) => {
            const q = e.target.value.trim().toLowerCase();
            card.querySelectorAll(".ms-option").forEach((opt) => {
              opt.hidden = q && !opt.dataset.text.includes(q);
            });
          });
          bindOptionChecks(card, id);
        }
      }

      card.querySelector("[data-text-input]")?.addEventListener("input", (e) => {
        state.filterValues[id] = e.target.value;
      });

      void meta;
    });
  }

  function bindOptionChecks(card, id) {
    card.querySelectorAll('.ms-option input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", () => {
        const selected = new Set(state.filterValues[id] || []);
        if (cb.checked) selected.add(cb.value);
        else selected.delete(cb.value);
        // For non-lazy: also sync from all visible checkboxes state for options currently shown
        if (card.dataset.lazy !== "1") {
          const fromDom = [...card.querySelectorAll('.ms-option input')].map((x) => [x.value, x.checked]);
          for (const [val, on] of fromDom) {
            if (on) selected.add(val);
            else selected.delete(val);
          }
        }
        state.filterValues[id] = [...selected];
        const control = card.querySelector(".ms-control");
        control.innerHTML = selected.size
          ? `<strong>Выбрано: ${selected.size}</strong><span>▼</span>`
          : `<span>Не выбрано — значит без ограничения</span><span>▼</span>`;
      });
    });
  }

  async function lazySearch(card, filterId, query) {
    const box = card.querySelector(".ms-options");
    const q = (query || "").trim();
    if (q.length < 2) {
      box.innerHTML = `<div class="ms-empty" data-lazy-hint>Введите минимум 2 символа для поиска</div>`;
      return;
    }
    box.innerHTML = `<div class="ms-empty">Ищем…</div>`;
    try {
      const dashId = state.dashboard.id;
      const data = await api(
        `/api/dashboards/${encodeURIComponent(dashId)}/filters/${encodeURIComponent(filterId)}/values?q=${encodeURIComponent(q)}&limit=80`
      );
      const selected = new Set(state.filterValues[filterId] || []);
      if (!data.values?.length) {
        box.innerHTML = `<div class="ms-empty">Ничего не найдено по «${escapeHtml(q)}»</div>`;
        return;
      }
      box.innerHTML = data.values
        .map(
          (val) => `
        <label class="ms-option" data-text="${escapeAttr(String(val).toLowerCase())}">
          <input type="checkbox" value="${escapeAttr(String(val))}" ${selected.has(val) ? "checked" : ""} />
          <span>${escapeHtml(String(val))}</span>
        </label>`
        )
        .join("");
      bindOptionChecks(card, filterId);
    } catch (err) {
      box.innerHTML = `<div class="ms-empty">Ошибка поиска: ${escapeHtml(err.message)}</div>`;
    }
  }

  function renderExports() {
    const root = $("#exports-root");
    const exports = state.dashboard?.exports || [];
    if (!exports.length) {
      root.innerHTML = `<p class="error">Для отчёта не настроены варианты выгрузки</p>`;
      return;
    }
    if (!state.exportId) state.exportId = exports[0].id;
    root.innerHTML = exports
      .map((e) => {
        const modeLabel =
          e.mode === "raw" ? "Полные данные" : e.mode === "bundle" ? "Архив ZIP" : "Сводка";
        return `
        <label class="export-item ${state.exportId === e.id ? "is-selected" : ""}">
          <input type="radio" name="export" value="${escapeAttr(e.id)}" ${state.exportId === e.id ? "checked" : ""} />
          <div>
            <h3>${escapeHtml(e.label)}</h3>
            <p>${escapeHtml(e.description || "")}</p>
            <span class="badge">${modeLabel}</span>
          </div>
        </label>`;
      })
      .join("");

    root.querySelectorAll("input[name=export]").forEach((inp) => {
      inp.addEventListener("change", () => {
        state.exportId = inp.value;
        root.querySelectorAll(".export-item").forEach((el) => el.classList.remove("is-selected"));
        inp.closest(".export-item").classList.add("is-selected");
      });
    });
  }

  function buildFiltersPayload() {
    const out = {};
    for (const f of state.filtersMeta) {
      const v = state.filterValues[f.id];
      if (f.type === "date_range") {
        if (v?.from && v?.to) out[f.id] = { from: v.from, to: v.to };
        continue;
      }
      if (f.type === "multi_select") {
        if (Array.isArray(v) && v.length) out[f.id] = v;
        continue;
      }
      if (v !== "" && v != null) out[f.id] = v;
    }
    return out;
  }

  function currentExport() {
    return state.dashboard?.exports?.find((e) => e.id === state.exportId);
  }

  function renderSummary() {
    const exp = currentExport();
    const filters = buildFiltersPayload();
    const filterText = Object.keys(filters).length
      ? Object.entries(filters)
          .map(([k, v]) => {
            const meta = state.filtersMeta.find((f) => f.id === k);
            const label = meta?.label || k;
            if (v && typeof v === "object" && !Array.isArray(v)) return `${label}: ${v.from} — ${v.to}`;
            if (Array.isArray(v)) return `${label}: ${v.length} зн.`;
            return `${label}: ${v}`;
          })
          .join("; ")
      : "без дополнительных ограничений";

    $("#summary").innerHTML = `
      <div class="summary-item"><span>Отчёт</span><strong>${escapeHtml(state.dashboard?.title || "—")}</strong></div>
      <div class="summary-item"><span>Файл</span><strong>${escapeHtml(exp?.label || "—")}</strong></div>
      <div class="summary-item"><span>Фильтры</span><strong>${escapeHtml(filterText)}</strong></div>`;

    $("#download-title").textContent =
      exp?.mode === "bundle" ? "Скачать архив ZIP" : "Скачать полный CSV";
    $("#btn-download").disabled = false;
  }

  async function loadPreview() {
    if (!state.dashboard || !state.exportId) return;
    const wrap = $("#preview-table-wrap");
    const err = $("#preview-error");
    const note = $("#preview-note");
    const meta = $("#preview-meta");
    err.hidden = true;
    note.hidden = true;
    wrap.innerHTML = `<div class="preview-placeholder">Загружаем образец данных…</div>`;
    $("#btn-download").disabled = true;
    try {
      const data = await api("/api/exports/preview", {
        method: "POST",
        body: JSON.stringify({
          dashboard_id: state.dashboard.id,
          export_id: state.exportId,
          filters: buildFiltersPayload(),
          limit: 100,
        }),
      });
      state.preview = data;
      if (data.note) {
        note.hidden = false;
        note.textContent = data.note;
      }
      meta.textContent = data.truncated
        ? `Показаны первые ${data.row_count} строк (это образец). Полный файл может быть больше.`
        : `Строк в образце: ${data.row_count}`;
      renderTable(data);
      $("#btn-download").disabled = false;
    } catch (e) {
      wrap.innerHTML = `<div class="preview-placeholder">Не удалось показать данные</div>`;
      err.hidden = false;
      err.textContent = e.message;
      toast("Ошибка превью");
    }
  }

  function renderTable(data) {
    const wrap = $("#preview-table-wrap");
    if (!data.rows?.length) {
      wrap.innerHTML = `<div class="preview-placeholder">По выбранным фильтрам строк нет. Измените условия и обновите превью.</div>`;
      return;
    }
    const cols = data.columns || Object.keys(data.rows[0] || {});
    const head = cols.map((c) => `<th title="${escapeAttr(c)}">${escapeHtml(c)}</th>`).join("");
    const body = data.rows
      .map(
        (row) =>
          `<tr>${cols
            .map((c) => `<td title="${escapeAttr(stringify(row[c]))}">${escapeHtml(stringify(row[c]))}</td>`)
            .join("")}</tr>`
      )
      .join("");
    wrap.innerHTML = `<table class="preview"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  async function downloadFull() {
    if (state.busy || !state.dashboard || !state.exportId) return;
    state.busy = true;
    const btn = $("#btn-download");
    const status = $("#download-status");
    btn.disabled = true;
    btn.textContent = "Готовим файл…";
    status.hidden = false;
    status.textContent = "Выполняется выгрузка, подождите…";
    try {
      const job = await api("/api/exports", {
        method: "POST",
        body: JSON.stringify({
          dashboard_id: state.dashboard.id,
          export_id: state.exportId,
          filters: buildFiltersPayload(),
        }),
      });
      if (job.status !== "done") {
        throw new Error(job.error || `Статус: ${job.status}`);
      }
      status.textContent = job.rows_written != null
        ? `Готово. Строк в файле: ${job.rows_written}. Скачивание…`
        : "Готово. Скачивание…";
      // trigger browser download
      const a = document.createElement("a");
      a.href = `/api/exports/${encodeURIComponent(job.job_id)}/download`;
      a.download = job.file_name || "export.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast("Файл скачивается");
    } catch (e) {
      status.textContent = `Ошибка: ${e.message}`;
      toast("Не удалось выгрузить");
    } finally {
      state.busy = false;
      btn.disabled = false;
      btn.textContent = "Скачать полный файл";
    }
  }

  function stringify(v) {
    if (v == null) return "";
    return String(v);
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replaceAll("'", "&#39;");
  }

  function bindGlobal() {
    $$(".tab").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.dataset.tab));
    });
    $$(".step").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        setStep(Number(btn.dataset.step));
      });
    });
    document.body.addEventListener("click", (e) => {
      const go = e.target.closest("[data-go]");
      if (go) setStep(Number(go.dataset.go));
    });
    $("#btn-to-preview").addEventListener("click", async () => {
      if (!state.exportId) {
        toast("Выберите, что скачать");
        return;
      }
      setStep(4);
      await loadPreview();
    });
    $("#btn-refresh-preview").addEventListener("click", loadPreview);
    $("#btn-download").addEventListener("click", downloadFull);
    $("#connect-form")?.addEventListener("submit", onConnectSubmit);
  }

  async function onConnectSubmit(e) {
    e.preventDefault();
    const raw = $("#connect-url").value.trim();
    const title = $("#connect-title").value.trim();
    const overwrite = $("#connect-overwrite").checked;
    const status = $("#connect-status");
    const err = $("#connect-error");
    const result = $("#connect-result");
    const btn = $("#btn-connect");
    err.hidden = true;
    result.hidden = true;
    status.hidden = false;
    status.textContent = "Читаем дашборд в Superset и создаём карточку…";
    btn.disabled = true;
    try {
      const body = {
        overwrite,
        title: title || null,
      };
      if (/^\d+$/.test(raw)) body.superset_dashboard_id = Number(raw);
      else body.superset_url = raw;

      const data = await api("/api/manifests/connect", {
        method: "POST",
        body: JSON.stringify(body),
      });
      status.textContent = "Готово";
      result.hidden = false;
      result.innerHTML = `
        <h3>${escapeHtml(data.title)}</h3>
        <p>Код отчёта: <code>${escapeHtml(data.manifest_id)}</code></p>
        <p>Таблица: <code>${escapeHtml(data.table)}</code></p>
        <p>Фильтров: ${data.filters_count}${data.native_filters_found != null ? ` (native в дашборде: ${data.native_filters_found})` : ""}, вариантов файла: ${data.exports_count}</p>
        ${Array.isArray(data.filter_labels) && data.filter_labels.length
          ? `<p><strong>Фильтры:</strong> ${data.filter_labels.map(escapeHtml).join(", ")}</p>`
          : ""}
        <p style="margin-top:.75rem">
          <button type="button" class="btn btn-primary" id="btn-go-export">Перейти к выгрузке</button>
        </p>`;
      $("#btn-go-export").addEventListener("click", async () => {
        setTab("export");
        await reloadDashboards();
        const dash = state.dashboards.find((d) => d.id === data.manifest_id);
        if (dash) await selectDashboard(dash);
      });
      toast("Отчёт подключён");
      await reloadDashboards();
    } catch (ex) {
      status.hidden = true;
      err.hidden = false;
      if (ex.status === 409) {
        err.textContent = `${ex.message} Поставьте галочку «Заменить…» и нажмите ещё раз.`;
      } else {
        err.textContent = ex.message;
      }
      toast("Не удалось подключить");
    } finally {
      btn.disabled = false;
    }
  }

  async function reloadDashboards() {
    const data = await api("/api/dashboards");
    state.dashboards = data.items || [];
    renderDashboards();
  }

  async function boot() {
    bindGlobal();
    try {
      await reloadDashboards();
    } catch (e) {
      $("#dashboards-error").hidden = false;
      $("#dashboards-error").textContent = `Не удалось загрузить список отчётов: ${e.message}`;
      $("#dashboard-grid").innerHTML = "";
    }
  }

  boot();
})();
