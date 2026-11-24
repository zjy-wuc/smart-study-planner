/* 独立视觉预览：所有数据均为示例，不访问业务接口或登录存储。 */
const copy = {
  brand: '学习计划', tagline: 'SMART STUDY PLANNER', workspace: '工作台',
  daily: '日常学习', review: '学习回顾', today: '今日任务', plans: '我的计划',
  history: '打卡历史', statistics: '学习统计', profile: '个人中心',
  motto: '把每一天的小小进步，<br>积累成想要的未来。', user: '学习者', account: '管理你的账户',
  search: '搜索示例计划', preview: '设计预览 · 示例数据', greeting: '今天，也向目标靠近一点。',
  subheading: '从一件小事开始，把学习慢慢变成习惯。', date: '11 月 17 日，星期二',
  pending: '3 项待完成', all: '查看全部', task: '任务 / 所属计划', progress: '完成情况', action: '快速打卡',
  checkin: '打卡', encouragement: '坚持就是胜利', active: '2 个进行中', create: '创建计划',
  steps: '步骤预览', detail: '计划详情', select: '当前预览计划',
  footer: '独立设计预览，数据与操作均为演示，不会修改学习记录。', reset: '重置演示',
  notice: '这是独立设计预览，该入口尚未连接真实页面。', saved: '演示打卡已记录，真实学习数据未发生变化。',
  invalid: '请输入安全范围内的非负整数。', empty: '没有匹配的示例计划', menu: '展开或收起导航',
  quantity: '累计完成数量', completed: '已完成', incomplete: '未完成', pendingStatus: '待完成', original: '目标',
  planStatus: '进行中', draft: '草稿', previewOnly: '只展示层级，不执行任务操作',
};
const paths = {
  book: '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Z"/><path d="M12 5v15"/>',
  home: '<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>',
  tasks: '<rect x="4" y="4" width="16" height="17" rx="3"/><path d="M9 3h6v4H9zM8 12l2 2 5-5M8 17h8"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4M17 3v4M3 11h18M8 15h2M14 15h2"/>',
  chart: '<path d="M4 3v18h17M8 16v-4M13 16V8M18 16V5"/>',
  history: '<path d="M3 11a9 9 0 1 1 2 7M3 5v6h6M12 7v6l4 2"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  folder: '<path d="M3 7V5h6l2 3h10v12H3Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
};
const icon = (name, cls = '') => `<svg class="icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${paths[name]}</svg>`;
const tasks = [
  { name: '完成极限与连续练习', path: '高等数学 / 第一章 · 函数与极限', actual: 12, target: 20, numeric: true },
  { name: '阅读一篇英语文章', path: '英语提升 / 阅读理解', numeric: false },
  { name: '复习核心词汇', path: '英语提升 / 词汇积累', actual: 30, target: 50, numeric: true },
  { name: '整理本周学习笔记', path: '高等数学 / 学习整理', numeric: false, done: true },
];
const plans = [
  { name: '高等数学 · 基础巩固', percent: 42, date: '11.01 — 12.15', note: '4 个学习步骤', status: 'active' },
  { name: '英语提升计划', percent: 68, date: '11.01 — 11.30', note: '3 个学习步骤', status: 'active' },
  { name: '计算机基础复习', percent: null, date: '11.20 — 12.20', note: '尚未开始', status: 'draft' },
];
const nav = (key, symbol, active = false) => `<a href="#${key}" class="nav-link ${active ? 'active' : ''}" ${active ? 'aria-current="page"' : ''} data-preview>${icon(symbol)}${copy[key]}</a>`;
const art = `<svg class="welcome-art" viewBox="0 0 210 125" fill="none" aria-hidden="true"><circle cx="156" cy="49" r="39" fill="#e5f2fc"/><circle cx="46" cy="84" r="25" fill="#e6f4ee"/><rect x="67" y="22" width="64" height="83" rx="7" fill="#8eb8ed"/><rect x="74" y="22" width="57" height="83" rx="5" fill="#c8dff9"/><path d="M86 43h29M86 51h20" stroke="#6e9cd3" stroke-width="3" stroke-linecap="round"/><path d="M110 22v24l6-5 6 5V22" fill="#4582d1"/><rect x="103" y="61" width="69" height="47" rx="5" fill="#a9d8c6"/><path d="M111 98h53" stroke="#f2faf6" stroke-width="5" stroke-linecap="round"/><path d="m143 34 3-7 3 7 7 3-7 3-3 7-3-7-7-3Z" fill="#dfb970"/><circle cx="46" cy="45" r="3" fill="#91b4df"/><path d="M38 110h144" stroke="#dbe6ef" stroke-width="2" stroke-linecap="round"/></svg>`;
document.querySelector('#app').innerHTML = `
<aside class="sidebar" id="navigation"><a class="brand" href="#workspace"><span class="brand-mark">${icon('book')}</span><span>${copy.brand}<small>${copy.tagline}</small></span></a><nav aria-label="${copy.daily}"><div class="nav-label">${copy.daily}</div>${nav('workspace','home',true)}${nav('today','tasks')}${nav('plans','calendar')}<div class="nav-label">${copy.review}</div>${nav('history','history')}${nav('statistics','chart')}</nav><div class="sidebar-bottom"><p class="sidebar-note">${copy.motto}</p><a class="profile" href="#profile" data-preview><span class="avatar">S</span><span><strong>${copy.profile}</strong><small>${copy.account}</small></span>${icon('chevron')}</a></div></aside>
<div class="shell"><header class="topbar"><div class="breadcrumb"><button class="mobile-menu" aria-label="${copy.menu}" aria-controls="navigation" aria-expanded="false">${icon('menu')}</button>${icon('home')}<span>/</span><strong>${copy.workspace}</strong></div><div class="top-actions"><span class="preview-label">${copy.preview}</span><label class="search">${icon('search')}<input type="search" id="search" placeholder="${copy.search}" aria-label="${copy.search}"></label><span class="avatar" aria-label="${copy.user}">S</span></div></header>
<main class="main"><section class="welcome"><div><h1>${copy.greeting}</h1><p>${copy.subheading}</p><div class="date" style="margin-top:13px">${icon('sun')}${copy.date}</div></div>${art}</section>
<section class="panel"><div class="panel-head"><div class="heading"><h2>${copy.today}</h2><span class="count" id="pending">${copy.pending}</span></div><a class="text-link" href="#today" data-preview>${copy.all}${icon('arrow')}</a></div><div class="task-columns"><span>${copy.task}</span><span>${copy.progress}</span><span>${copy.action}</span></div><div id="tasks"></div></section>
<div class="bottom-grid"><section class="panel"><div class="panel-head"><div class="heading"><h2>${copy.plans}</h2><span class="count">${copy.active}</span></div><a class="text-link" href="#create" data-preview>${icon('plus')}${copy.create}</a></div><div class="plan-list" id="plans"></div></section>
<section class="panel"><div class="panel-head"><div class="heading"><h2>${copy.steps}</h2></div><a href="#details" class="text-link" data-preview>${copy.detail}${icon('arrow')}</a></div><div class="step-body"><div class="select-label"><span>${plans[0].name}</span><small>${copy.select}</small></div><div class="tree"><details open><summary>${icon('chevron','chevron')}${icon('folder')}第一章 · 函数与极限</summary><ul><li>函数基础<span>完成型</span></li><li class="current">极限与连续练习<span>今日任务</span></li></ul></details><details open><summary>${icon('chevron','chevron')}${icon('folder')}第二章 · 导数与微分</summary><ul><li>导数计算<span>数量型</span></li></ul></details><details><summary>${icon('chevron','chevron')}${icon('folder')}学习整理</summary><ul><li>整理本周学习笔记<span>完成型</span></li></ul></details></div></div></section></div>
<footer class="footer"><span>${copy.footer}</span><button class="text-link" id="reset">${copy.reset}</button></footer></main></div><div class="toast" role="status" hidden></div>`;
function renderTasks(){document.querySelector('#tasks').innerHTML = tasks.map((task,index)=>`<form class="task-row" data-task="${index}"><div class="task-main"><span class="task-icon ${task.done?'green':''}">${icon(task.done?'check':task.numeric?'book':'tasks')}</span><div><div class="task-name">${task.name}</div><p class="task-path">${task.path}</p></div></div><div class="task-progress">${task.numeric?`<strong>${task.actual}</strong> / ${task.target}<small>${task.actual>=task.target?copy.completed:copy.incomplete}</small>`:`<small class="${task.done?'done':''}">${task.done?copy.completed:copy.pendingStatus}</small>`}</div><div class="task-action">${task.done?`<span class="success">${icon('check')}${copy.encouragement}</span>`:`${task.numeric?`<input class="quantity" type="number" min="0" step="1" value="${task.actual}" aria-label="${task.name}：${copy.quantity}" required>`:''}<button class="primary" type="submit">${copy.checkin}</button>`}</div></form>`).join('');}
function renderPlans(search=''){const selected=plans.filter(plan=>plan.name.includes(search));document.querySelector('#plans').innerHTML=selected.length?selected.map(plan=>`<article class="plan-item"><div class="plan-heading"><span class="book-icon">${icon('book')}</span><strong>${plan.name}</strong><span class="badge ${plan.status==='draft'?'neutral':''}">${plan.status==='draft'?copy.draft:copy.planStatus}</span></div>${plan.percent!==null?`<div class="plan-progress"><div class="plan-track" role="progressbar" aria-label="${plan.name}" aria-valuenow="${plan.percent}" aria-valuemin="0" aria-valuemax="100"><i style="width:${plan.percent}%"></i></div><span>${plan.percent}%</span></div>`:'<div style="height:13px"></div>'}<div class="plan-meta"><span>${plan.date}</span><span>${plan.note}</span></div></article>`).join(''):`<p class="empty">${copy.empty}</p>`;}
let timer;function notify(message){const toast=document.querySelector('.toast');toast.textContent=message;toast.hidden=false;clearTimeout(timer);timer=setTimeout(()=>toast.hidden=true,3200);}
document.addEventListener('click',event=>{const link=event.target.closest('[data-preview]');if(link){event.preventDefault();notify(copy.notice);}});
document.querySelector('#tasks').addEventListener('submit',event=>{event.preventDefault();const form=event.target;const task=tasks[Number(form.dataset.task)];if(task.numeric){const quantity=Number(form.querySelector('input').value);if(!Number.isSafeInteger(quantity)||quantity<0){notify(copy.invalid);return;}task.actual=quantity;}task.done=true;renderTasks();notify(copy.saved);});
document.querySelector('#search').addEventListener('input',event=>renderPlans(event.target.value.trim()));
document.querySelector('.mobile-menu').addEventListener('click',event=>{const open=document.querySelector('.sidebar').classList.toggle('open');event.currentTarget.setAttribute('aria-expanded',String(open));});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){document.querySelector('.sidebar').classList.remove('open');document.querySelector('.mobile-menu').setAttribute('aria-expanded','false');}});
document.querySelector('#reset').addEventListener('click',()=>location.reload());
renderTasks();renderPlans();
