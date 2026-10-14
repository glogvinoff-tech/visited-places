(() => {
  "use strict";
  const layout = document.querySelector(".app-layout");
  if (!layout) return;
  const view = layout.dataset.view;
  const profile = JSON.parse(document.getElementById("profile-data").textContent);
  const initial = JSON.parse(document.getElementById("initial-data").textContent);
  const content = document.getElementById("content");
  const status = document.getElementById("status");
  const dialog = document.getElementById("record-dialog");
  const form = document.getElementById("record-form");
  const fieldContainer = document.getElementById("form-fields");
  const deleteDialog = document.getElementById("delete-dialog");
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const state = { page: initial.page, pages: initial.pages, pageSize: initial.page_size, detail: initial.detail || false, records: initial.results, places: [], trips: [], revision: 0 };
  let current = null;
  let deleting = null;
  let toastTimer;

  function node(tag, className = "", text = "") {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== "") item.textContent = String(text);
    return item;
  }

  function icon(name) {
    const item = node("i");
    item.dataset.lucide = name;
    item.setAttribute("aria-hidden", "true");
    return item;
  }

  function renderIcons() { if (window.lucide) window.lucide.createIcons(); }

  function iconButton(name, title, action, kind = "") {
    const button = node("button", `icon-button ${kind}`);
    button.type = "button";
    button.title = title;
    button.setAttribute("aria-label", title);
    button.append(icon(name));
    if (action) button.addEventListener("click", action);
    return button;
  }

  async function api(url, method = "GET", data) {
    const options = { method, credentials: "same-origin", headers: { Accept: "application/json" } };
    if (method !== "GET") {
      options.headers["X-CSRFToken"] = csrf;
      options.headers["Content-Type"] = "application/json";
      if (data !== undefined) options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    if (response.status === 401) {
      window.location.assign(`${profile.login_url}?next=${encodeURIComponent(window.location.pathname)}`);
      throw new Error("Войдите в аккаунт.");
    }
    let payload;
    try { payload = await response.json(); }
    catch { throw new Error("Сервер не ответил. Повторите попытку."); }
    if (!response.ok) {
      const problem = new Error(payload.error || "Действие не выполнено.");
      problem.fields = payload.errors || {};
      throw problem;
    }
    return payload;
  }

  function toast(message) {
    const item = document.getElementById("toast");
    item.textContent = message;
    item.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { item.hidden = true; }, 3200);
  }

  function formatDate(value) {
    return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(`${value.slice(0, 10)}T12:00:00`));
  }

  function placePhoto(place, className) {
    if (!place.image) {
      const fallback = node("div", `${className} photo-placeholder`);
      fallback.append(icon("map-pin"));
      return fallback;
    }
    const image = node("img", className);
    image.src = place.image;
    image.alt = place.name;
    image.loading = "lazy";
    if (className === "place-photo" && place.credit?.height > place.credit?.width) {
      image.style.objectFit = "contain";
    }
    preparePhoto(image);
    return image;
  }

  function preparePhoto(image) {
    const showFallback = () => {
      const fallback = node("div", `${image.className} photo-placeholder`);
      fallback.append(icon("map-pin"));
      image.replaceWith(fallback);
      renderIcons();
    };
    if (image.complete && !image.naturalWidth) showFallback();
    else image.addEventListener("error", showFallback, { once: true });
  }

  function placeCell(place, title = place.name, url = place.url) {
    const cell = node("div", "place-cell");
    const words = node("div");
    const link = node("a", "record-title", title);
    link.href = url;
    words.append(link);
    words.append(node("span", "record-subtitle", `${place.city}, ${place.country}`));
    cell.append(placePhoto(place, "table-photo"), words);
    return cell;
  }

  function actions(resource, record) {
    const group = node("div", "actions");
    if (resource === "visits" || profile.is_staff) {
      for (const [action, name, title, kind] of [["edit", "pencil", "Редактировать", ""], ["delete", "trash-2", "Удалить", "delete"]]) {
        const button = iconButton(name, title, null, kind);
        button.dataset.recordAction = action;
        button.dataset.resource = resource;
        button.dataset.recordId = record.id;
        group.append(button);
      }
    }
    return group;
  }

  function rating(value) {
    if (value === null) return node("span", "record-subtitle", "Без оценки");
    const item = node("span", "rating");
    item.append(icon("star"), node("span", "", `${value}/5`));
    return item;
  }

  function table(headers) {
    const wrapper = node("div", "table-wrap");
    const element = node("table", "records-table");
    const head = node("thead");
    const row = node("tr");
    headers.forEach(label => row.append(node("th", "", label)));
    head.append(row);
    const body = node("tbody");
    element.append(head, body);
    wrapper.append(element);
    return { wrapper, body };
  }

  function td(child, label = "", className = "") {
    const item = node("td", className);
    if (label) item.dataset.label = label;
    item.append(child);
    return item;
  }

  function renderVisits(records) {
    const result = table(["Место", "Дата", "Поездка", "Оценка", "Заметка", ""]);
    records.forEach(record => {
      const row = node("tr");
      const date = node("div", "date-text", formatDate(record.visited_at));
      date.append(node("span", "record-subtitle", record.visited_at.slice(11, 16)));
      const note = node("div", "note", record.note || "Нет заметки");
      note.title = record.note;
      row.append(
        td(placeCell(record.trip.place, record.trip.place.name, record.url)), td(date, "Дата"),
        td(Object.assign(node("a", "record-title", record.trip.name), { href: record.trip.url }), "Поездка"),
        td(rating(record.rating), "Оценка"), td(note, "Заметка", "cell-note"),
        td(actions("visits", record))
      );
      result.body.append(row);
    });
    content.append(result.wrapper);
  }

  function renderTrips(records) {
    const result = table(["Поездка и место", "Начало", "Окончание", "Посещений", ""]);
    records.forEach(record => {
      const row = node("tr");
      const title = placeCell(record.place, record.name, record.url);
      title.querySelector(".record-subtitle").textContent = `${record.place.name}, ${record.place.city}`;
      row.append(td(title), td(node("span", "date-text", formatDate(record.start_date)), "Начало"),
        td(node("span", "date-text", formatDate(record.end_date)), "Окончание"),
        td(node("span", "", record.visit_count), "Посещений"), td(actions("trips", record)));
      result.body.append(row);
    });
    content.append(result.wrapper);
  }

  function renderPlaces(records) {
    const grid = node("div", "places-grid");
    records.forEach(place => {
      const card = node("article", "place-card");
      const body = node("div", "place-card-body");
      const location = node("p", "location");
      location.append(icon("map-pin"), node("span", "", `${place.city}, ${place.country}`));
      const bottom = node("div", "card-bottom");
      bottom.append(node("span", "category", place.category), actions("places", place));
      const heading = node("h3");
      const link = node("a", "", place.name);
      link.href = place.url;
      heading.append(link);
      body.append(heading, location, bottom);
      card.append(placePhoto(place, "place-photo"), body);
      if (place.credit) {
        const credit = node("a", "photo-credit", `Фото: ${place.credit.author} · ${place.credit.license}`);
        credit.href = place.credit.source;
        credit.target = "_blank";
        credit.rel = "noopener";
        credit.title = `${place.credit.author} (${place.credit.license})`;
        card.append(credit);
      }
      grid.append(card);
    });
    content.append(grid);
  }

  function empty(message) {
    const area = node("div", "empty-state");
    area.append(icon(view === "visits" ? "notebook-pen" : "map-pin"), node("h2", "", message));
    content.append(area);
  }

  async function loadRecords() {
    const revision = ++state.revision;
    status.textContent = "";
    content.setAttribute("aria-busy", "true");
    content.replaceChildren();
    const loading = node("div", "loading");
    loading.append(icon("loader-circle"), node("span", "", "Загрузка..."));
    content.append(loading);
    renderIcons();
    const query = new URLSearchParams({ page: state.page, page_size: state.pageSize });
    const search = document.getElementById("search").value.trim();
    if (search) query.set("q", search);
    if (view === "visits") {
      const trip = document.getElementById("trip-filter").value;
      const from = document.getElementById("date-from").value;
      const to = document.getElementById("date-to").value;
      if (trip) query.set("trip", trip);
      if (from) query.set("from", from);
      if (to) query.set("to", to);
    }
    try {
      const data = await api(`/api/${view}/?${query}`);
      if (revision !== state.revision) return;
      state.records = data.results;
      state.pages = data.pages;
      content.replaceChildren();
      if (!data.results.length) empty(view === "visits" ? "Посещений не найдено" : "Записей не найдено");
      else ({ visits: renderVisits, places: renderPlaces, trips: renderTrips })[view](data.results);
      document.getElementById("record-count").textContent = `Записей: ${data.count}`;
      document.getElementById("page-number").textContent = `${data.page} / ${data.pages}`;
      document.getElementById("previous").disabled = data.page <= 1;
      document.getElementById("next").disabled = data.page >= data.pages;
      document.getElementById("previous").value = data.page - 1;
      document.getElementById("next").value = data.page + 1;
      document.getElementById("pagination").hidden = !data.count;
    } catch (problem) {
      if (revision !== state.revision) return;
      content.replaceChildren();
      status.textContent = problem.message;
      document.getElementById("pagination").hidden = true;
    } finally {
      if (revision === state.revision) content.setAttribute("aria-busy", "false");
      renderIcons();
    }
  }

  function renderStatistics(data) {
    content.replaceChildren();
    content.setAttribute("aria-busy", "false");
    const more = node("div", "stat-more");
    for (const [label, value] of [["Городов", data.cities], ["Поездок", data.trips], ["Оценено посещений", ""]]) {
      if (value === "") continue;
      const item = node("span", "", label);
      item.append(node("strong", "", value));
      more.append(item);
    }
    content.append(more);
    if (!data.visits) { empty("Посещений пока нет"); return; }
    const columns = node("div", "statistics-layout");
    const countries = node("section");
    countries.append(node("h2", "", "Посещения по странам"));
    const maximum = Math.max(...data.by_country.map(item => item.count), 1);
    data.by_country.forEach(item => {
      const row = node("div", "country-row");
      const label = node("div");
      label.append(node("span", "", item.name), node("strong", "", item.count));
      const track = node("div", "bar-track");
      const fill = node("div", "bar-fill");
      fill.style.width = `${Math.round(item.count / maximum * 100)}%`;
      track.append(fill);
      row.append(label, track);
      countries.append(row);
    });
    const places = node("section");
    places.append(node("h2", "", "Чаще посещаемые места"));
    data.top_places.forEach(item => {
      const row = node("div", "top-place");
      const words = node("div", "record-title", item.name);
      words.append(node("small", "", `${item.city}, ${item.country}`));
      row.append(words, node("strong", "", item.count));
      places.append(row);
    });
    columns.append(countries, places);
    content.append(columns);
  }

  async function loadMetrics() {
    try {
      const data = await api("/api/statistics/");
      document.querySelectorAll("[data-metric]").forEach(item => {
        const value = data[item.dataset.metric];
        item.textContent = value === null ? "Нет" : item.dataset.metric === "average_rating" ? value.toFixed(2) : value;
      });
      if (view === "statistics") renderStatistics(data);
    } catch (problem) { status.textContent = problem.message; }
  }

  async function refresh() {
    if (view === "statistics") await loadMetrics();
    else await Promise.all([loadRecords(), loadMetrics()]);
  }

  async function allRecords(resource) {
    let page = 1;
    const results = [];
    while (true) {
      const data = await api(`/api/${resource}/?page_size=200&page=${page}`);
      results.push(...data.results);
      if (page >= data.pages) return results;
      page += 1;
    }
  }

  async function loadChoices() {
    [state.places, state.trips] = await Promise.all([allRecords("places"), allRecords("trips")]);
    const filter = document.getElementById("trip-filter");
    if (filter) {
      const selected = filter.value;
      filter.replaceChildren(new Option("Все поездки", ""));
      state.trips.forEach(trip => filter.append(new Option(trip.name, trip.id)));
      filter.value = selected;
    }
  }

  function addField(name, label, type, value = "", options = {}) {
    const field = node("div", `form-field${options.wide ? " wide" : ""}`);
    const text = node("label", "", label);
    text.htmlFor = `field-${name}`;
    const control = node(type === "select" ? "select" : type === "textarea" ? "textarea" : "input");
    control.id = `field-${name}`;
    control.name = name;
    if (control.tagName === "INPUT") control.type = type;
    if (options.required) control.required = true;
    if (options.max) control.maxLength = options.max;
    if (options.options) options.options.forEach(([id, title]) => control.append(new Option(title, id)));
    control.value = value ?? "";
    const error = node("span", "field-error");
    error.id = `error-${name}`;
    control.setAttribute("aria-describedby", error.id);
    field.append(text, control, error);
    fieldContainer.append(field);
    return control;
  }

  async function openForm(resource, record = null) {
    document.getElementById("form-errors").textContent = "";
    const save = document.getElementById("save-button");
    save.disabled = false;
    current = { resource, record };
    fieldContainer.replaceChildren();
    try {
      if (resource !== "me") await loadChoices();
      const labels = { visits: "посещение", trips: "поездку", places: "место", me: "профиль" };
      document.getElementById("dialog-title").textContent = resource === "me" ? "Мой профиль" : `${record ? "Редактировать" : "Добавить"} ${labels[resource]}`;
      if (resource === "places") {
        addField("name", "Название места", "text", record?.name, { required: true, max: 160, wide: true });
        addField("city", "Город", "text", record?.city, { required: true, max: 100 });
        addField("country", "Страна", "text", record?.country, { required: true, max: 100 });
        addField("category", "Категория", "text", record?.category, { required: true, max: 60, wide: true });
        addField("image_url", "Адрес фотографии", "url", record?.image_url, { wide: true, max: 500 });
      } else if (resource === "trips") {
        if (!state.places.length) { toast("Сначала добавьте место."); return; }
        addField("name", "Название поездки", "text", record?.name, { required: true, max: 160, wide: true });
        addField("place", "Место", "select", record?.place.id ?? state.places[0].id, {
          required: true, wide: true, options: state.places.map(place => [place.id, `${place.name}, ${place.city}`])
        });
        const today = new Date().toLocaleDateString("sv-SE");
        const start = addField("start_date", "Начало", "date", record?.start_date ?? today, { required: true });
        const end = addField("end_date", "Окончание", "date", record?.end_date ?? today, { required: true });
        start.addEventListener("change", () => { end.min = start.value; });
        end.min = start.value;
      } else if (resource === "visits") {
        if (!state.trips.length) { toast("Сначала добавьте поездку."); return; }
        const trip = addField("trip", "Поездка", "select", record?.trip.id ?? state.trips[0].id, {
          required: true, wide: true,
          options: state.trips.map(item => [item.id, `${item.name} (${formatDate(item.start_date)})`])
        });
        const selected = () => state.trips.find(item => item.id === Number(trip.value));
        const date = addField("visited_at", "Дата посещения", "datetime-local", record?.visited_at ?? `${selected().start_date}T12:00`, { required: true, wide: true });
        const bounds = () => {
          const item = selected();
          date.min = `${item.start_date}T00:00`;
          date.max = `${item.end_date}T23:59`;
          if (!record && (date.value < date.min || date.value > date.max)) date.value = `${item.start_date}T12:00`;
        };
        trip.addEventListener("change", bounds);
        bounds();
        addField("rating", "Оценка", "select", record?.rating ?? "", {
          wide: true, options: [["", "Без оценки"], ...[1, 2, 3, 4, 5].map(value => [value, `${value} / 5`])]
        });
        addField("note", "Заметка", "textarea", record?.note, { wide: true, max: 2000 });
      } else {
        const data = await api("/api/me/");
        addField("name", "Имя", "text", data.name, { required: true, max: 150, wide: true });
        addField("email", "Email", "email", data.email, { required: true, wide: true });
        if (profile.is_staff) {
          const link = node("a", "button secondary", "Администрирование");
          link.href = profile.admin_url;
          fieldContainer.append(link);
        }
      }
      dialog.showModal();
      renderIcons();
      fieldContainer.querySelector("input,select")?.focus();
    } catch (problem) { toast(problem.message); }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const save = document.getElementById("save-button");
    if (save.disabled) return;
    save.disabled = true;
    document.getElementById("form-errors").textContent = "";
    fieldContainer.querySelectorAll(".field-error").forEach(item => { item.textContent = ""; });
    const data = Object.fromEntries(new FormData(form));
    for (const key of ["place", "trip", "rating"]) {
      if (key in data) data[key] = data[key] === "" ? null : Number(data[key]);
    }
    const { resource, record } = current;
    const url = resource === "me" ? "/api/me/" : `/api/${resource}/${record ? `${record.id}/` : ""}`;
    try {
      const result = await api(url, record || resource === "me" ? "PATCH" : "POST", data);
      dialog.close();
      if (resource === "me") {
        profile.name = result.name;
        document.getElementById("profile-name").textContent = result.name;
        document.querySelector(".avatar").textContent = result.name[0];
      } else {
        if (state.detail) { window.location.reload(); return; }
        state.page = 1;
        await loadChoices();
        await refresh();
      }
      toast("Изменения сохранены.");
    } catch (problem) {
      document.getElementById("form-errors").textContent = problem.message;
      for (const [field, errors] of Object.entries(problem.fields || {})) {
        const target = document.getElementById(`error-${field}`);
        if (target) target.textContent = errors.join(" ");
        else document.getElementById("form-errors").textContent += ` ${errors.join(" ")}`;
      }
    } finally { save.disabled = false; }
  });

  function openDelete(resource, record) {
    deleting = { resource, record };
    document.getElementById("delete-description").textContent = record.name || `${record.trip.place.name} · ${formatDate(record.visited_at)}`;
    document.getElementById("delete-error").textContent = "";
    document.getElementById("confirm-delete").disabled = false;
    deleteDialog.showModal();
  }

  document.getElementById("confirm-delete").addEventListener("click", async () => {
    const button = document.getElementById("confirm-delete");
    button.disabled = true;
    try {
      await api(`/api/${deleting.resource}/${deleting.record.id}/`, "DELETE");
      deleteDialog.close();
      if (state.detail) { window.location.assign(initial.list_url); return; }
      state.page = 1;
      await loadChoices();
      await refresh();
      toast("Запись удалена.");
    } catch (problem) { document.getElementById("delete-error").textContent = problem.message; }
    finally { button.disabled = false; }
  });
  document.getElementById("cancel-delete").addEventListener("click", () => deleteDialog.close());
  document.getElementById("close-dialog").addEventListener("click", () => dialog.close());
  document.getElementById("cancel-dialog").addEventListener("click", () => dialog.close());
  document.getElementById("profile-button").addEventListener("click", () => openForm("me"));
  document.getElementById("add-button")?.addEventListener("click", () => openForm(view));
  document.getElementById("filters-form")?.addEventListener("submit", event => {
    event.preventDefault();
    state.page = 1;
    refresh();
  });
  document.getElementById("previous").addEventListener("click", event => { event.preventDefault(); if (state.page > 1) { state.page -= 1; loadRecords(); } });
  document.getElementById("next").addEventListener("click", event => { event.preventDefault(); if (state.page < state.pages) { state.page += 1; loadRecords(); } });
  layout.addEventListener("click", event => {
    const button = event.target.closest("[data-record-action]");
    if (!button) return;
    const record = state.records.find(item => item.id === Number(button.dataset.recordId));
    if (!record) return;
    if (button.dataset.recordAction === "edit") openForm(button.dataset.resource, record);
    else openDelete(button.dataset.resource, record);
  });
  content.querySelectorAll("[data-place-photo]").forEach(preparePhoto);
  let searchTimer;
  document.getElementById("search")?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.page = 1; loadRecords(); }, 250);
  });
  for (const id of ["trip-filter", "date-from", "date-to"]) {
    document.getElementById(id)?.addEventListener("change", () => { state.page = 1; loadRecords(); });
  }
  renderIcons();
})();
