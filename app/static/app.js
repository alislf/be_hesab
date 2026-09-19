const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); tg.setHeaderColor('#0F172A'); tg.setBackgroundColor('#F8FAFC'); }

const faDigits = '۰۱۲۳۴۵۶۷۸۹';
const fa = n => String(n).replace(/\d/g, d => faDigits[d]);
const money = n => `${fa(Math.abs(Number(n || 0)).toLocaleString('en-US'))} تومان`;
const initials = name => (name || 'ب').trim().split(/\s+/).slice(0, 2).map(x => x[0]).join('');
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

const state = { me: null, friends: [], expenses: [], activeFriend: null, transactions: [], selectedDate: null, dateTarget: null, calendar: null };
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

function authHeaders() {
  const headers = {'Content-Type':'application/json'};
  if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;
  else if (['localhost','127.0.0.1'].includes(location.hostname) || new URLSearchParams(location.search).has('demo')) headers['X-Demo-User'] = localStorage.demoUser || '900001';
  return headers;
}

async function api(path, options={}) {
  const res = await fetch(path, {...options, headers:{...authHeaders(), ...(options.headers||{})}});
  let data={}; try { data=await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.detail || 'خطایی رخ داد. دوباره تلاش کنید.');
  return data;
}

function toast(text, error=false) {
  const el=$('#toast'); el.textContent=text; el.className=`toast show${error?' error':''}`;
  clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.className='toast',2600);
}

function avatar(user, id='') {
  return `<div class="avatar"${id?` id="${id}"`:''}>${user.photo_url?`<img src="${esc(user.photo_url)}" alt="">`:esc(initials(user.name))}</div>`;
}

function jalaliText(iso, withWeekday=false) {
  const date=new Date(`${iso}T12:00:00`);
  return new Intl.DateTimeFormat('fa-IR-u-ca-persian',{weekday:withWeekday?'long':undefined,year:'numeric',month:'long',day:'numeric'}).format(date);
}

function balanceInfo(value, friendName='دوستت') {
  if (value>0) return {cls:'positive', amount:money(value), label:`از ${friendName} طلبکاری`};
  if (value<0) return {cls:'negative', amount:money(value), label:`به ${friendName} بدهکاری`};
  return {cls:'settled', amount:'تسویه', label:'حساب صاف است'};
}

async function loadAll() {
  try {
    state.me=await api('/api/me');
    [state.friends,state.expenses]=await Promise.all([api('/api/friends'),api('/api/expenses')]);
    renderHeader(); renderFriends(); renderExpenses(); renderProfile();
    $('#loading').classList.add('done');
  } catch(err) {
    $('#loading').innerHTML=`<div class="offline"><div class="loader-logo">بـ</div><h1>ورود به بحساب انجام نشد</h1><p>${esc(err.message)}</p></div>`;
  }
}

function renderHeader() {
  $('#today-label').textContent=jalaliText(state.me.today,true);
  const count=state.me.pending_requests;
  $('#badge').textContent=fa(count); $('#badge').classList.toggle('hidden',!count);
}

function renderFriends() {
  const net=state.friends.reduce((sum,f)=>sum+f.balance,0), info=balanceInfo(net,'دوستانت');
  $('#net-balance').textContent=info.amount;
  $('#net-balance').className=info.cls==='settled'?'':info.cls;
  $('#net-caption').textContent=net===0?'همه‌چیز سر حساب است':info.label;
  const list=$('#friends-list');
  if (!state.friends.length) { list.innerHTML=`<div class="empty"><span>♧</span><strong>هنوز دوستی اضافه نکرده‌ای</strong><p>نام کاربری دوستت را وارد کن و پس از تأیید، حساب دونفره‌تان را شروع کنید.</p></div>`; return; }
  list.innerHTML=state.friends.map(f=>{const b=balanceInfo(f.balance,f.first_name);return `<article class="friend-card" data-friend="${f.id}">${avatar(f)}<div class="card-main"><strong>${esc(f.name)}</strong><small>${f.username?'@'+esc(f.username):'بدون نام کاربری'}</small></div><div class="balance-tag ${b.cls}"><strong>${b.amount}</strong><small>${b.label}</small></div></article>`}).join('');
  $$('.friend-card').forEach(el=>el.onclick=()=>openFriend(Number(el.dataset.friend)));
}

function renderExpenses() {
  const total=state.expenses.reduce((s,x)=>s+x.amount,0); $('#expenses-total').textContent=money(total);
  const list=$('#expenses-list');
  if(!state.expenses.length){list.innerHTML=`<div class="empty"><span>◫</span><strong>هزینه‌ای ثبت نشده</strong><p>اولین هزینه شخصی‌ات را ثبت کن تا همیشه تصویر روشنی از مخارجت داشته باشی.</p></div>`;return}
  list.innerHTML=state.expenses.map(x=>`<article class="expense-card"><div class="type-icon type-payment">◫</div><div class="card-main"><strong>${esc(x.description)}</strong><small>${jalaliText(x.happened_on)} ${x.is_edited?'<span class="edited">ویرایش شده</span>':''}</small></div><div><div class="amount negative">${money(x.amount)}</div><div class="expense-actions"><button class="mini-btn" data-edit-expense="${x.id}">✎</button><button class="mini-btn delete" data-delete-expense="${x.id}">×</button></div></div></article>`).join('');
  $$('[data-edit-expense]').forEach(b=>b.onclick=()=>openExpense(Number(b.dataset.editExpense)));
  $$('[data-delete-expense]').forEach(b=>b.onclick=()=>confirmDelete('این هزینه شخصی حذف شود؟',()=>deleteExpense(Number(b.dataset.deleteExpense))));
}

function renderProfile() {
  const u=state.me; $('#profile-name').textContent=u.name; $('#profile-username').textContent=u.username?`@${u.username}`:'بدون نام کاربری';
  $('#profile-avatar').innerHTML=u.photo_url?`<img src="${esc(u.photo_url)}" alt="">`:esc(initials(u.name));
  $('#profile-friends').textContent=fa(u.friends_count); $('#profile-expenses').textContent=fa(Number(u.expenses_total).toLocaleString('en-US'));
}

async function openFriend(id) {
  try {
    const data=await api(`/api/friends/${id}/transactions`); state.activeFriend=data.friend; state.transactions=data.transactions;
    $('#detail-name').textContent=data.friend.name; $('#detail-username').textContent=data.friend.username?`@${data.friend.username}`:'حساب دونفره';
    $('#detail-avatar').innerHTML=data.friend.photo_url?`<img src="${esc(data.friend.photo_url)}" alt="">`:esc(initials(data.friend.name));
    const b=balanceInfo(data.balance,data.friend.first_name);
    $('#detail-balance').innerHTML=`<span>مانده فعلی حساب</span><strong class="${b.cls}">${b.amount}</strong><small class="${b.cls}">${b.label}</small>`;
    renderTransactions(); $('#friend-detail').classList.remove('hidden'); document.body.style.overflow='hidden';
  } catch(e){toast(e.message,true)}
}

function renderTransactions() {
  const list=$('#transactions-list');
  if(!state.transactions.length){list.innerHTML=`<div class="empty"><span>↕</span><strong>گردش حسابی وجود ندارد</strong><p>بدهی یا پرداخت جدیدی ثبت کن.</p></div>`;return}
  const meta={debt:['بدهی','↓','type-debt'],payment:['پرداخت','↑','type-payment'],settlement:['تسویه','✓','type-settlement']};
  list.innerHTML=state.transactions.map(x=>{const m=meta[x.kind];return `<article class="transaction-card"><div class="type-icon ${m[2]}">${m[1]}</div><div><h4>${m[0]} ${x.is_edited?'<span class="edited">ویرایش شده</span>':''}</h4><p>${esc(x.direction_text)}<br>${esc(x.description)||'بدون توضیح'} · ${jalaliText(x.happened_on)}<br>ثبت‌کننده: ${esc(x.creator_name)}</p></div><div><div class="amount">${money(x.amount)}</div>${x.can_edit?`<div class="transaction-actions"><button class="mini-btn" data-edit-tx="${x.id}">✎</button><button class="mini-btn delete" data-delete-tx="${x.id}">×</button></div>`:''}</div></article>`}).join('');
  $$('[data-edit-tx]').forEach(b=>b.onclick=()=>openTransaction('edit',Number(b.dataset.editTx)));
  $$('[data-delete-tx]').forEach(b=>b.onclick=()=>confirmDelete('این تراکنش حذف شود؟ مانده حساب دوباره محاسبه خواهد شد.',()=>deleteTransaction(Number(b.dataset.deleteTx))));
}

async function refreshFriend(){if(state.activeFriend)await openFriend(state.activeFriend.id); state.friends=await api('/api/friends');renderFriends()}

function openTransaction(kind,id=null){
  const edit=id!==null, item=edit?state.transactions.find(x=>x.id===id):null;
  $('#transaction-id').value=id||''; $('#transaction-kind').value=edit?item.kind:kind;
  $('#transaction-title').textContent=edit?'ویرایش تراکنش':({debt:'ثبت بدهی جدید',payment:'ثبت پرداخت',settlement:'تسویه حساب'}[kind]);
  $('#direction-label').classList.toggle('hidden',edit||kind==='settlement'); $('#amount-label').classList.toggle('hidden',kind==='settlement'&&!edit);
  const select=$('#transaction-direction');
  if(kind==='debt') select.innerHTML=`<option value="me_to_friend">من به ${esc(state.activeFriend.first_name)} بدهکار شدم</option><option value="friend_to_me">${esc(state.activeFriend.first_name)} به من بدهکار شد</option>`;
  else select.innerHTML=`<option value="me_to_friend">من به ${esc(state.activeFriend.first_name)} پرداخت کردم</option><option value="friend_to_me">${esc(state.activeFriend.first_name)} به من پرداخت کرد</option>`;
  $('#transaction-amount').value=item?fa(item.amount.toLocaleString('en-US')):''; $('#transaction-description').value=item?.description||'';
  setDateButton($('#transaction-date'),item?.happened_on||state.me.today); $('#transaction-modal').showModal();
}

function openExpense(id=null){const item=id?state.expenses.find(x=>x.id===id):null;$('#expense-id').value=id||'';$('#expense-title').textContent=id?'ویرایش هزینه':'ثبت هزینه شخصی';$('#expense-amount').value=item?fa(item.amount.toLocaleString('en-US')):'';$('#expense-description').value=item?.description||'';setDateButton($('#expense-date'),item?.happened_on||state.me.today);$('#expense-modal').showModal()}
function normalizeNumber(v){return Number(String(v).replace(/[۰-۹]/g,d=>String(faDigits.indexOf(d))).replace(/[^0-9]/g,''))}
function formatMoneyInput(e){const n=normalizeNumber(e.target.value);e.target.value=n?fa(n.toLocaleString('en-US')):''}

async function submitTransaction(e){e.preventDefault();const id=Number($('#transaction-id').value),kind=$('#transaction-kind').value;const body={kind,amount:normalizeNumber($('#transaction-amount').value),description:$('#transaction-description').value,happened_on:$('#transaction-date').dataset.iso,direction:$('#transaction-direction').value};try{if(id)await api(`/api/transactions/${id}`,{method:'PUT',body:JSON.stringify({amount:body.amount,description:body.description,happened_on:body.happened_on})});else await api(`/api/friends/${state.activeFriend.id}/transactions`,{method:'POST',body:JSON.stringify(body)});$('#transaction-modal').close();toast(id?'تراکنش ویرایش شد':'تراکنش ثبت شد');await refreshFriend()}catch(err){toast(err.message,true)}}
async function deleteTransaction(id){try{await api(`/api/transactions/${id}`,{method:'DELETE'});toast('تراکنش حذف شد');await refreshFriend()}catch(e){toast(e.message,true)}}
async function submitExpense(e){e.preventDefault();const id=Number($('#expense-id').value),body={amount:normalizeNumber($('#expense-amount').value),description:$('#expense-description').value,happened_on:$('#expense-date').dataset.iso};try{await api(id?`/api/expenses/${id}`:'/api/expenses',{method:id?'PUT':'POST',body:JSON.stringify(body)});$('#expense-modal').close();state.expenses=await api('/api/expenses');state.me=await api('/api/me');renderExpenses();renderProfile();toast(id?'هزینه ویرایش شد':'هزینه ثبت شد')}catch(err){toast(err.message,true)}}
async function deleteExpense(id){try{await api(`/api/expenses/${id}`,{method:'DELETE'});state.expenses=await api('/api/expenses');state.me=await api('/api/me');renderExpenses();renderProfile();toast('هزینه حذف شد')}catch(e){toast(e.message,true)}}

async function loadRequests(){try{const items=await api('/api/friend-requests');const list=$('#requests-list');list.innerHTML=items.length?items.map(x=>`<article class="request-card">${avatar(x.sender)}<div class="card-main"><strong>${esc(x.sender.name)}</strong><small>${x.sender.username?'@'+esc(x.sender.username):''}</small></div><div class="request-actions"><button class="accept" data-request="${x.id}" data-answer="1">قبول</button><button class="reject" data-request="${x.id}" data-answer="0">رد</button></div></article>`).join(''):`<div class="empty"><span>♢</span><strong>درخواستی نداری</strong><p>درخواست‌های جدید اینجا نمایش داده می‌شوند.</p></div>`;$$('[data-request]').forEach(b=>b.onclick=()=>respondRequest(Number(b.dataset.request),b.dataset.answer==='1'));if(!$('#requests-modal').open)$('#requests-modal').showModal()}catch(e){toast(e.message,true)}}
async function respondRequest(id,accept){try{await api(`/api/friend-requests/${id}/respond`,{method:'POST',body:JSON.stringify({accept})});state.me=await api('/api/me');state.friends=await api('/api/friends');renderHeader();renderFriends();await loadRequests();toast(accept?'دوست جدید اضافه شد':'درخواست رد شد')}catch(e){toast(e.message,true)}}

function confirmDelete(text,action){$('#confirm-text').textContent=text;$('#confirm-modal').showModal();$('#confirm-delete').onclick=async()=>{$('#confirm-modal').close();await action()}}

// Lightweight Jalali calendar conversion (Gregorian dates remain the API storage format).
function div(a,b){return Math.trunc(a/b)} function mod(a,b){return a-Math.trunc(a/b)*b}
function jalCal(jy){const breaks=[-61,9,38,199,426,686,756,818,1111,1181,1210,1635,2060,2097,2192,2262,2324,2394,2456,3178];let gy=jy+621,leapJ=-14,jp=breaks[0],jump=0;if(jy<jp||jy>=breaks.at(-1))throw Error('Invalid Jalali year');for(let i=1;i<breaks.length;i++){const jm=breaks[i];jump=jm-jp;if(jy<jm)break;leapJ+=div(jump,33)*8+div(mod(jump,33),4);jp=jm}let n=jy-jp;leapJ+=div(n,33)*8+div(mod(n,33)+3,4);if(mod(jump,33)===4&&jump-n===4)leapJ++;const leapG=div(gy,4)-div((div(gy,100)+1)*3,4)-150;const march=20+leapJ-leapG;if(jump-n<6)n=n-jump+div(jump+4,33)*33;let leap=mod(mod(n+1,33)-1,4);if(leap===-1)leap=4;return{leap,gy,march}}
function g2d(gy,gm,gd){let d=div((gy+div(gm-8,6)+100100)*1461,4)+div(153*mod(gm+9,12)+2,5)+gd-34840408;d=d-div(div(gy+100100+div(gm-8,6),100)*3,4)+752;return d}
function d2g(jdn){let j=4*jdn+139361631;j=j+div(div(4*jdn+183187720,146097)*3,4)*4-3908;const i=div(mod(j,1461),4)*5+308;const gd=div(mod(i,153),5)+1,gm=mod(div(i,153),12)+1,gy=div(j,1461)-100100+div(8-gm,6);return{gy,gm,gd}}
function j2d(jy,jm,jd){const r=jalCal(jy);return g2d(r.gy,3,r.march)+(jm-1)*31-div(jm,7)*(jm-7)+jd-1}
function d2j(jdn){const g=d2g(jdn),jy=g.gy-621,r=jalCal(jy),jdn1f=g2d(g.gy,3,r.march);let k=jdn-jdn1f;if(k>=0){if(k<=185)return{jy,jm:1+div(k,31),jd:mod(k,31)+1};k-=186}else{const jy2=jy-1;k+=179;if(r.leap===1)k++;return{jy:jy2,jm:7+div(k,30),jd:mod(k,30)+1}}return{jy,jm:7+div(k,30),jd:mod(k,30)+1}}
function isoToJ(iso){const [y,m,d]=iso.split('-').map(Number);return d2j(g2d(y,m,d))} function jToIso(y,m,d){const g=d2g(j2d(y,m,d));return `${g.gy}-${String(g.gm).padStart(2,'0')}-${String(g.gd).padStart(2,'0')}`}
const jMonths=['فروردین','اردیبهشت','خرداد','تیر','مرداد','شهریور','مهر','آبان','آذر','دی','بهمن','اسفند'];
function setDateButton(btn,iso){btn.dataset.iso=iso;btn.textContent=jalaliText(iso,true)}
function openCalendar(target){state.dateTarget=target;const j=isoToJ(target.dataset.iso||state.me.today);state.calendar={year:j.jy,month:j.jm,selected:j};renderCalendar();$('#calendar-modal').showModal()}
function renderCalendar(){const c=state.calendar;$('#cal-title').textContent=`${jMonths[c.month-1]} ${fa(c.year)}`;const days=c.month<=6?31:c.month<=11?30:(jalCal(c.year).leap===0?30:29);const g=d2g(j2d(c.year,c.month,1));const weekday=(new Date(g.gy,g.gm-1,g.gd).getDay()+1)%7;let html='<span class="blank"></span>'.repeat(weekday);const today=isoToJ(state.me.today);for(let d=1;d<=days;d++){const isToday=today.jy===c.year&&today.jm===c.month&&today.jd===d,isSelected=c.selected.jy===c.year&&c.selected.jm===c.month&&c.selected.jd===d;html+=`<button class="${isToday?'today ':''}${isSelected?'selected':''}" data-day="${d}">${fa(d)}</button>`}$('#calendar-grid').innerHTML=html;$$('[data-day]').forEach(b=>b.onclick=()=>{const iso=jToIso(c.year,c.month,Number(b.dataset.day));setDateButton(state.dateTarget,iso);$('#calendar-modal').close()})}
function changeMonth(step){let {year,month}=state.calendar;month+=step;if(month<1){month=12;year--}if(month>12){month=1;year++}state.calendar.year=year;state.calendar.month=month;renderCalendar()}

$$('.nav-item').forEach(b=>b.onclick=()=>{$$('.nav-item').forEach(x=>x.classList.toggle('active',x===b));$$('.page').forEach(p=>p.classList.toggle('active',p.dataset.page===b.dataset.target))});
$('#add-friend-btn').onclick=()=>{$('#friend-form').reset();$('#friend-modal').showModal()};
$('#friend-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/friend-requests',{method:'POST',body:JSON.stringify({username:$('#friend-username').value})});$('#friend-modal').close();toast('درخواست دوستی ارسال شد')}catch(err){toast(err.message,true)}};
$('#notifications-btn').onclick=loadRequests;$('#requests-modal [data-close]').onclick=()=>$('#requests-modal').close();
$('#add-expense-btn').onclick=()=>openExpense();$('#expense-form').onsubmit=submitExpense;$('#transaction-form').onsubmit=submitTransaction;
$('#detail-back').onclick=()=>{$('#friend-detail').classList.add('hidden');document.body.style.overflow=''};
$$('[data-transaction]').forEach(b=>b.onclick=()=>openTransaction(b.dataset.transaction));
$$('.money-input').forEach(x=>x.addEventListener('input',formatMoneyInput));
$('#transaction-date').onclick=e=>openCalendar(e.currentTarget);$('#expense-date').onclick=e=>openCalendar(e.currentTarget);
$('#cal-next').onclick=()=>changeMonth(1);$('#cal-prev').onclick=()=>changeMonth(-1);$('#calendar-today').onclick=()=>{setDateButton(state.dateTarget,state.me.today);$('#calendar-modal').close()};
$('#confirm-cancel').onclick=()=>$('#confirm-modal').close();

loadAll();
