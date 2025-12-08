const STORAGE_KEY = 'tm_tool_tasks_v1';

const defaultTasks = [
  { title: "✔ Design project layout", status: "Completed", createdAt: new Date().toISOString() },
  { title: "📝 Write project report", status: "In Progress", createdAt: new Date().toISOString() },
  { title: "🚀 Prepare PPT presentation", status: "Pending", createdAt: new Date().toISOString() }
];

function loadTasks() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(defaultTasks));
    return defaultTasks.slice();
  }
  try {
    return JSON.parse(raw);
  } catch (e) {
    console.error('Failed to parse tasks storage', e);
    return defaultTasks.slice();
  }
}

function saveTasks(tasks) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
}

function renderTasks() {
  const container = document.getElementById('tasksContainer');
  if (!container) return; // page may not have tasks

  container.innerHTML = '';
  const tasks = loadTasks();

  if (!tasks || tasks.length === 0) {
    const p = document.createElement('div');
    p.className = 'no-tasks';
    p.textContent = 'No tasks yet — add your first task above.';
    container.appendChild(p);
    return;
  }

  tasks.forEach((task, index) => {
    const box = document.createElement('div');
    box.className = 'task-box';
    if (task.status === 'Completed') box.classList.add('completed');

    const header = document.createElement('div');
    header.className = 'task-header';

    const titleEl = document.createElement('h3');
    titleEl.className = 'task-title';
    titleEl.textContent = task.title;

    const meta = document.createElement('div');
    meta.className = 'task-meta';
    const date = new Date(task.createdAt);
    meta.textContent = `${task.status} • ${date.toLocaleString()}`;

    const actions = document.createElement('div');
    actions.className = 'actions';

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'btn btn-toggle';
    toggleBtn.textContent = task.status === 'Completed' ? 'Mark Pending' : 'Mark Completed';
    toggleBtn.onclick = () => toggleStatus(index);

    const delBtn = document.createElement('button');
    delBtn.className = 'btn btn-delete';
    delBtn.textContent = 'Delete';
    delBtn.onclick = () => deleteTask(index);

    actions.appendChild(toggleBtn);
    actions.appendChild(delBtn);

    header.appendChild(titleEl);
    header.appendChild(actions);

    box.appendChild(header);
    box.appendChild(meta);

    container.appendChild(box);
  });
}

function addTask(title) {
  if (!title || !title.trim()) {
    alert('Please enter a valid task.');
    return;
  }
  const tasks = loadTasks();
  const newTask = {
    title: title.trim(),
    status: 'Pending',
    createdAt: new Date().toISOString()
  };
  tasks.unshift(newTask);
  saveTasks(tasks);
  renderTasks();
  const input = document.getElementById('taskInput');
  if (input) { input.value=''; input.focus(); }
}

function toggleStatus(index) {
  const tasks = loadTasks();
  if (!tasks[index]) return;
  tasks[index].status = tasks[index].status === 'Completed' ? 'Pending' : 'Completed';
  saveTasks(tasks);
  renderTasks();
}

function deleteTask(index) {
  if (!confirm('Delete this task?')) return;
  const tasks = loadTasks();
  tasks.splice(index, 1);
  saveTasks(tasks);
  renderTasks();
}

document.addEventListener('DOMContentLoaded', () => {
  renderTasks();
  const addBtn = document.getElementById('addBtn');
  const input = document.getElementById('taskInput');

  if (addBtn && input) {
    addBtn.addEventListener('click', () => addTask(input.value));
    input.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); addTask(input.value); }
    });
  }
});
