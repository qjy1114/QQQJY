const titleInput = document.getElementById("taskTitle");
const dueDateInput = document.getElementById("taskDueDate");
const priorityInput = document.getElementById("taskPriority");
const addButton = document.getElementById("addButton");
const searchInput = document.getElementById("searchInput");
const filterButtons = document.querySelectorAll(".filters button");
const todoColumn = document.getElementById("todoColumn");
const inProgressColumn = document.getElementById("inProgressColumn");
const doneColumn = document.getElementById("doneColumn");
const taskCount = document.getElementById("taskCount");
const todoCount = document.getElementById("todoCount");
const inProgressCount = document.getElementById("inProgressCount");
const doneCount = document.getElementById("doneCount");

let tasks = [];
let activePriorityFilter = "all";
let searchKeyword = "";
const STATUS_ORDER = ["todo", "in-progress", "done"];
const STATUS_LABELS = {
  "todo": "待办",
  "in-progress": "进行中",
  "done": "已完成",
};

async function fetchTasks() {
  const response = await fetch("/api/tasks");
  tasks = await response.json();
  renderTasks();
}

async function addTask() {
  const title = titleInput.value.trim();
  if (!title) return;

  const payload = {
    title,
    dueDate: dueDateInput.value,
    priority: priorityInput.value,
    status: "todo",
  };

  const response = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.ok) {
    titleInput.value = "";
    dueDateInput.value = "";
    priorityInput.value = "medium";
    await fetchTasks();
  }
}

async function updateTask(taskId, payload) {
  await fetch(`/api/tasks/${taskId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await fetchTasks();
}

async function deleteTask(taskId) {
  await fetch(`/api/tasks/${taskId}`, { method: "DELETE" });
  await fetchTasks();
}

async function editTask(taskId) {
  const task = tasks.find((item) => item.id === taskId);
  if (!task) return;

  const newTitle = prompt("编辑任务标题：", task.title);
  if (newTitle === null) return;

  const newDueDate = prompt("编辑截止日期（YYYY-MM-DD，可留空）：", task.dueDate || "") || "";
  const newPriority = prompt("编辑优先级（low / medium / high）：", task.priority) || task.priority;

  await updateTask(taskId, {
    title: newTitle.trim() || task.title,
    dueDate: newDueDate.trim(),
    priority: ["low", "medium", "high"].includes(newPriority) ? newPriority : task.priority,
  });
}

function setPriorityFilter(filter) {
  activePriorityFilter = filter;
  filterButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === filter);
  });
  renderTasks();
}

function setSearchKeyword(value) {
  searchKeyword = value.trim().toLowerCase();
  renderTasks();
}

function matchesFilter(task) {
  const matchesPriority = activePriorityFilter === "all" || task.priority === activePriorityFilter;
  const text = `${task.title} ${task.description || ""}`.toLowerCase();
  const matchesSearch = !searchKeyword || text.includes(searchKeyword);
  return matchesPriority && matchesSearch;
}

function renderTasks() {
  const boardTasks = {
    todo: [],
    "in-progress": [],
    done: [],
  };

  tasks.filter(matchesFilter).forEach((task) => {
    const status = STATUS_ORDER.includes(task.status) ? task.status : "todo";
    boardTasks[status].push(task);
  });

  todoColumn.innerHTML = "";
  inProgressColumn.innerHTML = "";
  doneColumn.innerHTML = "";

  renderColumn(boardTasks.todo, todoColumn);
  renderColumn(boardTasks["in-progress"], inProgressColumn);
  renderColumn(boardTasks.done, doneColumn);

  todoCount.textContent = boardTasks.todo.length;
  inProgressCount.textContent = boardTasks["in-progress"].length;
  doneCount.textContent = boardTasks.done.length;

  const totalCount = tasks.length;
  const doneTasks = tasks.filter((task) => task.status === "done").length;
  taskCount.textContent = `${totalCount} 个任务，${doneTasks} 个已完成`;
}

function renderColumn(taskList, container) {
  if (taskList.length === 0) {
    container.innerHTML = "<li class='empty-state'>当前列表暂无任务。</li>";
    return;
  }

  taskList.forEach((task) => {
    const item = document.createElement("li");
    item.className = `task-card priority-${task.priority}`;

    item.innerHTML = `
      <strong>${escapeHtml(task.title)}</strong>
      <div class="task-meta">
        <span class="badge badge-${escapeHtml(task.priority)}">${escapeHtml(task.priority)}</span>
        <span>${task.dueDate ? `截止：${escapeHtml(task.dueDate)}` : "无截止"}</span>
      </div>
      <div class="task-details">${escapeHtml(task.description || "无描述")}</div>
      <div class="task-actions">
        <select aria-label="更改状态" data-action="status">
          <option value="todo" ${task.status === "todo" ? "selected" : ""}>待办</option>
          <option value="in-progress" ${task.status === "in-progress" ? "selected" : ""}>进行中</option>
          <option value="done" ${task.status === "done" ? "selected" : ""}>已完成</option>
        </select>
        <button data-action="edit">编辑</button>
        <button data-action="delete">删除</button>
      </div>
    `;

    const statusSelect = item.querySelector("select[data-action='status']");
    statusSelect.addEventListener("change", () => updateTask(task.id, { status: statusSelect.value }));

    const editButton = item.querySelector("button[data-action='edit']");
    editButton.addEventListener("click", () => editTask(task.id));

    const deleteButton = item.querySelector("button[data-action='delete']");
    deleteButton.addEventListener("click", () => deleteTask(task.id));

    container.appendChild(item);
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

addButton.addEventListener("click", addTask);
searchInput.addEventListener("input", (event) => setSearchKeyword(event.target.value));

filterButtons.forEach((button) => {
  button.addEventListener("click", () => setPriorityFilter(button.dataset.filter));
});

dueDateInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    addTask();
  }
});

titleInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    addTask();
  }
});

fetchTasks();
