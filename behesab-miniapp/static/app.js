const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const initData = tg?.initData || '';
const devId = new URLSearchParams(location.search).get('dev') || '';
let me = null, currentFriend = null, editingTx = null, editingPersonal = null;
const fa = n => Number(n||0).toLocaleString('fa-IR');
const money = n => `${fa(Math.round(n))} تومان`;
const $ = s => document.querySelector(s);
const escapeHtml = s => String(s??'').replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':'&quot;'}[c]));

async function api(path, opts={}){
  const headers = {'Content-Type':'application/json', ...(opts.headers||{})};
  if(initData) headers['X-Telegram-Init-Data']=initData;
  if(devId) headers['X-Dev-Telegram-Id']=devId;
  const r = await fetch(path,{...opts,headers});
  const data = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.detail||'خطا در ارتباط با سرور');
  return data;
}
function toast(msg){ const t=$('#toast'); t.textContent=msg;t.classList.remove('hidden');setTimeout(()=>t.classList.add('hidden'),2500); }
function openSheet(html){ $('#sheetContent').innerHTML=html;$('#sheet').classList.remove('hidden'); }
function closeSheet(){ $('#sheet').classList.add('hidden'); currentFriend=null;editingTx=null;editingPersonal=null; }
$('#sheet').addEventListener('click',e=>{if(e.target.id==='sheet')closeSheet()});

function balanceText(v){ if(v>0)return `<span class="balance positive">${money(v)} طلبکار</span>`; if(v<0)return `<span class="balance negative">${money(Math.abs(v))} بدهکار</span>`;return `<span class="balance zero">تسویه</span>`; }

async function loadMe(){ me=await api('/api/me');$('#profileName').textContent=me.display_name;$('#profileUsername').textContent=me.username?'@'+me.username:'Telegram ID: '+me.telegram_id;$('#profileAvatar').textContent=(me.first_name||'ب')[0]; }
async function loadFriends(){ const list=await api('/api/friends');$('#friendsList').innerHTML=list.length?list.map(f=>`<div class="friend-card" onclick="openFriend(${f.id})"><div class="avatar">${escapeHtml((f.first_name||'ب')[0])}</div><div class="grow"><div class="name">${escapeHtml(f.display_name)}</div><div class="muted">${f.username?'@'+escapeHtml(f.username):'حساب دونفره'}</div></div>${balanceText(f.balance)}</div>`).join(''):'<div class="empty">هنوز دوستی اضافه نکرده‌ای.</div>';const total=list.reduce((a,b)=>a+b.balance,0);$('#totalBalance').textContent=(total>=0?'+':'−')+money(Math.abs(total)); }
async function loadRequests(){ const rows=await api('/api/friends/requests'); const b=$('#requestBadge');b.textContent=rows.length;b.classList.toggle('hidden',!rows.length);return rows; }

$('#addFriendBtn').onclick=()=>openSheet(`<h2>افزودن دوست</h2><p class="muted">نام کاربری تلگرام یا Telegram ID را وارد کن. طرف مقابل باید قبلاً بحساب را باز کرده باشد.</p><label>نام کاربری / ID</label><input id="friendTarget" placeholder="مثلاً @ali یا 123456789"><div class="actions"><button class="primary" onclick="sendFriendRequest()">ارسال درخواست</button><button class="ghost" onclick="closeSheet()">انصراف</button></div>`);
async function sendFriendRequest(){try{await api('/api/friends/requests',{method:'POST',body:JSON.stringify({target:$('#friendTarget').value})});toast('درخواست دوستی ارسال شد');closeSheet()}catch(e){toast(e.message)}}
window.sendFriendRequest=sendFriendRequest;

$('#bellBtn').onclick=async()=>{try{const rows=await loadRequests();openSheet(`<h2>درخواست‌های دوستی</h2><div class="stack">${rows.length?rows.map(r=>`<div class="request-card"><b>${escapeHtml(r.from_user.display_name)}</b><div class="muted">${r.from_user.username?'@'+escapeHtml(r.from_user.username):''}</div><div class="request-actions"><button class="primary" onclick="actRequest(${r.id},'accept')">تأیید</button><button class="ghost" onclick="actRequest(${r.id},'reject')">رد</button></div></div>`).join(''):'<div class="empty">درخواستی نداری.</div>'}</div>`)}catch(e){toast(e.message)}};
async function actRequest(id,action){try{await api(`/api/friends/requests/${id}/${action}`,{method:'POST'});toast(action==='accept'?'دوستی تأیید شد':'درخواست رد شد');closeSheet();await Promise.all([loadFriends(),loadRequests()])}catch(e){toast(e.message)}}
window.actRequest=actRequest;

async function openFriend(id){try{const d=await api(`/api/friends/${id}/transactions`);currentFriend=d.friend;renderFriend(d)}catch(e){toast(e.message)}}
window.openFriend=openFriend;
function renderFriend(d){openSheet(`<div class="friend-header"><div class="avatar">${escapeHtml((d.friend.first_name||'ب')[0])}</div><div><h2 style="margin:0">${escapeHtml(d.friend.display_name)}</h2><div class="muted">${d.friend.username?'@'+escapeHtml(d.friend.username):''}</div></div></div><div class="friend-summary">مانده فعلی: ${balanceText(d.balance)}</div><div class="top-actions"><button class="primary" onclick="showTxForm('debt')">ثبت بدهی</button><button class="ghost" onclick="showTxForm('settlement')">ثبت تسویه</button></div><div class="divider"></div><h3>ریز تراکنش‌ها</h3><div class="stack">${d.transactions.length?d.transactions.map(txCard).join(''):'<div class="empty">هنوز تراکنشی ثبت نشده.</div>'}</div>`)}
function txCard(t){const dir={i_owe:'من بدهکارم',they_owe:'او بدهکار است',i_paid:'من پرداخت کردم',they_paid:'او پرداخت کرد'}[t.direction];return `<div class="tx-card"><div><div class="name">${escapeHtml(t.title)}</div><div class="tx-amount ${t.kind==='settlement'?'positive':''}">${money(t.amount)}</div><div class="tx-meta">${dir} · ${new Date(t.created_at).toLocaleDateString('fa-IR')}</div>${t.note?`<div class="muted">${escapeHtml(t.note)}</div>`:''}</div><div class="tx-actions"><button class="link-btn" onclick='editTx(${JSON.stringify(t)})'>ویرایش</button><button class="danger" onclick="deleteTx(${t.id})">حذف</button></div></div>`}
function showTxForm(kind='debt',t=null){editingTx=t;const isDebt=kind==='debt';const dir=t?.direction||(isDebt?'they_owe':'i_paid');openSheet(`<h2>${t?'ویرایش':'ثبت'} ${isDebt?'بدهی':'تسویه'}</h2><label>نوع</label><select id="txKind" onchange="syncDirections()"><option value="debt" ${kind==='debt'?'selected':''}>بدهی</option><option value="settlement" ${kind==='settlement'?'selected':''}>تسویه</option></select><label>جهت</label><select id="txDirection"></select><label>مبلغ (تومان)</label><input id="txAmount" type="number" min="1" value="${t?.amount||''}"><label>عنوان</label><input id="txTitle" value="${escapeHtml(t?.title||'')}"><label>یادداشت</label><textarea id="txNote">${escapeHtml(t?.note||'')}</textarea><div class="actions"><button class="primary" onclick="saveTx()">ذخیره</button><button class="ghost" onclick="openFriend(${currentFriend.id})">بازگشت</button></div>`);syncDirections(dir)}
window.showTxForm=showTxForm;
function syncDirections(selected){const k=$('#txKind').value;$('#txDirection').innerHTML=k==='debt'?`<option value="they_owe">او به من بدهکار است</option><option value="i_owe">من به او بدهکارم</option>`:`<option value="i_paid">من پرداخت کردم</option><option value="they_paid">او پرداخت کرد</option>`;if(selected)$('#txDirection').value=selected}
window.syncDirections=syncDirections;
function editTx(t){showTxForm(t.kind,t)} window.editTx=editTx;
async function saveTx(){try{const body={kind:$('#txKind').value,direction:$('#txDirection').value,amount:Number($('#txAmount').value),title:$('#txTitle').value,note:$('#txNote').value};if(editingTx)await api(`/api/transactions/${editingTx.id}`,{method:'PUT',body:JSON.stringify(body)});else await api(`/api/friends/${currentFriend.id}/transactions`,{method:'POST',body:JSON.stringify(body)});toast('تراکنش ذخیره شد');await openFriend(currentFriend.id);await loadFriends()}catch(e){toast(e.message)}} window.saveTx=saveTx;
async function deleteTx(id){if(!confirm('این تراکنش حذف شود؟'))return;try{await api(`/api/transactions/${id}`,{method:'DELETE'});toast('تراکنش حذف شد');await openFriend(currentFriend.id);await loadFriends()}catch(e){toast(e.message)}} window.deleteTx=deleteTx;

async function loadPersonal(){try{const rows=await api('/api/personal');$('#personalList').innerHTML=rows.length?rows.map(x=>`<div class="expense-card"><div class="tx-card"><div><div class="name">${escapeHtml(x.title)}</div><div class="tx-amount">${money(x.amount)}</div><div class="tx-meta">${new Date(x.created_at).toLocaleDateString('fa-IR')}</div>${x.note?`<div class="muted">${escapeHtml(x.note)}</div>`:''}</div><div class="tx-actions"><button class="link-btn" onclick='showPersonalForm(${JSON.stringify(x)})'>ویرایش</button><button class="danger" onclick="deletePersonal(${x.id})">حذف</button></div></div></div>`).join(''):'<div class="empty">هنوز هزینه شخصی ثبت نکرده‌ای.</div>'}catch(e){toast(e.message)}}
$('#addPersonalBtn').onclick=()=>showPersonalForm();
function showPersonalForm(x=null){editingPersonal=x;openSheet(`<h2>${x?'ویرایش':'ثبت'} هزینه شخصی</h2><label>مبلغ (تومان)</label><input id="pAmount" type="number" value="${x?.amount||''}"><label>عنوان</label><input id="pTitle" value="${escapeHtml(x?.title||'')}"><label>یادداشت</label><textarea id="pNote">${escapeHtml(x?.note||'')}</textarea><div class="actions"><button class="primary" onclick="savePersonal()">ذخیره</button><button class="ghost" onclick="closeSheet()">انصراف</button></div>`)} window.showPersonalForm=showPersonalForm;
async function savePersonal(){try{const b={amount:Number($('#pAmount').value),title:$('#pTitle').value,note:$('#pNote').value};if(editingPersonal)await api(`/api/personal/${editingPersonal.id}`,{method:'PUT',body:JSON.stringify(b)});else await api('/api/personal',{method:'POST',body:JSON.stringify(b)});toast('ذخیره شد');closeSheet();loadPersonal()}catch(e){toast(e.message)}} window.savePersonal=savePersonal;
async function deletePersonal(id){if(!confirm('این هزینه حذف شود؟'))return;try{await api(`/api/personal/${id}`,{method:'DELETE'});toast('حذف شد');loadPersonal()}catch(e){toast(e.message)}} window.deletePersonal=deletePersonal;

$('.bottom-nav').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;document.querySelectorAll('.bottom-nav button').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));$('#view'+b.dataset.view).classList.add('active');if(b.dataset.view==='Personal')loadPersonal()});

(async()=>{try{await loadMe();await Promise.all([loadFriends(),loadRequests(),loadPersonal()])}catch(e){document.body.innerHTML=`<div style="padding:40px;text-align:center;font-family:Tahoma"><h2>بحساب</h2><p>${escapeHtml(e.message)}</p><p style="color:#64748B">اپ را از دکمه داخل ربات Telegram باز کنید.</p></div>`}})();
