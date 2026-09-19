const $ = (s, root = document) => root.querySelector(s);
const icons = {
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z"/><path d="M9 21v-8h6v8"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.4 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z"/>',
  shield: '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 4v2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>',
  book: '<path d="M5 3h14v18H5a2 2 0 0 1 0-4h14M3 19V5a2 2 0 0 1 2-2"/><circle cx="12" cy="8" r="2"/><path d="M9 14a3 3 0 0 1 6 0"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  settings: '<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  logout: '<path d="M9 21H4V3h5m5 4 5 5-5 5m-5-5h13"/>',
  leaf: '<path d="M20 4C7 1 1 10 7 16s15 0 13-12Z"/><path d="M4 21 16 9"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
  edit: '<path d="m15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-4-4L5 15Z"/>',
};
const icon = (name, cls = '') => `<svg class="icon ${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.home}</svg>`;
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const brand = () => `<button class="brand" data-action="landing"><span class="brand-mark">${icon('home')}</span>FrontPorch<span class="brand-period">.</span></button>`;
let screen = 'landing';
let section = 'overview';

function landing() {
  return `<div class="landing"><header class="landing-header">${brand()}<nav aria-label="Welcome"><a href="#how-it-works">How it works</a><button class="text-button" data-action="login">Log in</button><button class="button small" data-action="signup">Join the neighborhood ${icon('arrow')}</button></nav></header>
  <main id="main"><section class="hero"><div class="hero-copy"><div class="eyebrow"><span class="tiny-line"></span> SMALL CIRCLES. REAL CONNECTION.</div><h1>A little less screen.<br>A little more <em>hello.</em></h1><p>A phone of their own. A circle you trust.<br>Give your kids the freedom to call their favorite people, with you close by.</p><div class="hero-actions"><button class="button large" data-action="signup">Set up your family ${icon('arrow')}</button><button class="text-button" data-action="demo">Take a look around</button></div><div class="hero-proof">${icon('shield')} Parent-approved. Private by design.</div></div>
  <div class="hero-stage"><div class="stage-heading"><span>THE MAPLE FAMILY</span><span>${icon('lock')} Your little corner</span></div><div class="phone-preview"><div class="preview-icon">${icon('phone')}</div><div class="eyebrow">A FAMILIAR PLACE TO CALL</div><h2>Lily’s phone</h2><span class="pill green">${icon('check')} Ready for a hello</span><div class="preview-people"><div><span class="avatar lavender">E</span><span>Emma</span><small>A friend next door</small></div><div><span class="avatar yellow">G</span><span>Grandma</span><small>A familiar voice</small></div><div><span class="avatar blue">M</span><span>Mom</span><small>Always in their corner</small></div></div><div class="preview-footer">${icon('shield')} Only the people you’ve approved</div></div><div class="stage-note"><span>More “can you come over?”</span><span>Less scrolling.</span></div><div class="stage-caption">Good old-fashioned connection.<br>A thoughtful new way to get there.</div></div></section>
  <section class="how-section" id="how-it-works"><div class="section-heading"><div><div class="eyebrow">A SMALL START. A CLOSER CIRCLE.</div><h2>Make room for real conversations.</h2></div><span class="muted">Their independence. Your peace of mind.</span></div><div class="how-grid"><article><span class="step-label">01 / AT HOME</span><h3>Start with your family.</h3><p>Add your children and give each phone a familiar name. No accounts for the kids.</p></article><article><span class="step-label">02 / IN GOOD COMPANY</span><h3>Choose their circle.</h3><p>Connect with families you know. Calling starts when both families approve.</p></article><article><span class="step-label">03 / JUST PICK UP</span><h3>Let the hellos happen.</h3><p>A simple phone, trusted contacts, and room for conversations without a screen.</p></article></div></section>
  </main><footer class="landing-footer"><span>FrontPorch. A phone is a place.</span><span>Emergency calling is not available. Keep another phone for emergencies.</span></footer></div>`;
}
function nextDemoExtension(data,start=6100) {
  const used=new Set([...data.children.map(c=>c.extension),...Object.values(data.contactExtensions||{})]);
  for(let offset=0;offset<9000;offset++) {
    const extension=String(1000+(start-1000+offset)%9000);
    if(!used.has(extension))return extension;
  }
  return '';
}
function contactExtension(data,phone,previous='') {
  data.contactExtensions ||= {};
  const existing=data.contactExtensions[phone]||previous;
  const occupied=data.children.some(c=>c.extension===existing)||Object.entries(data.contactExtensions).some(([number,extension])=>number!==phone&&extension===existing);
  const extension=/^[1-9][0-9]{3}$/.test(existing)&&!occupied?existing:nextDemoExtension(data);
  if(extension)data.contactExtensions[phone]=extension;
  return extension;
}
function migrateDemo(data) {
  data.contactExtensions ||= {};
  for(const contact of data.contacts||[]) {
    contact.extension=contactExtension(data,contact.phone,contact.extension);
    delete contact.outgoing;
    delete contact.incoming;
  }
  delete data.outsideEnabled;
  for (const child of data.children) {
    child.shortcuts ||= [];
    for(const shortcut of child.shortcuts) {
      try {
        const [kind,target]=JSON.parse(shortcut.target);
        const contact=kind==='contact'?(data.contacts||[]).find(c=>c.id===target):null;
        if(contact)shortcut.target=JSON.stringify(['contact',contact.phone]);
      } catch { /* An invalid old destination remains unavailable. */ }
    }
  }
  data.guardians ||= [];
  data.guardianInvites ||= [];
  data.directoryListed = data.directoryListed === true;
  data.inviteCode ||= 'MAPLE-9Q4T';
  for (const family of data.families) {
    if (Array.isArray(family.connections)) continue;
    family.peers = [...new Set(family.incoming || [])];
    family.connections = [];
    for (const member of family.outgoing || []) {
      for (const peer of family.peers) {
        const request = data.invites.find(i => i.direction === 'outgoing' && i.status === 'pending' && i.family.toLowerCase() === family.name.toLowerCase() && i.childIds.includes(member.childId));
        if (member.status === 'approved' || request) {
          family.connections.push({childId:member.childId,peer,status:member.status,...(request ? {requestId:request.id} : {})});
          if (request) request.peers = [...family.peers];
        }
      }
    }
    for (const [index,peer] of family.peers.entries()) {
      const approved = family.connections.filter(c => c.peer === peer && c.status === 'approved');
      const previous = data.invites.find(i => i.direction === 'incoming' && i.family.toLowerCase() === family.name.toLowerCase() && i.child === peer && i.status === 'accepted');
      if (approved.length && previous) { previous.reciprocal = true; previous.acceptedChildIds = approved.map(c=>c.childId); }
      // A former one-way approval must be reviewed, rather than silently broadened.
      if (!approved.length && !data.invites.some(i=>i.direction==='incoming' && i.family.toLowerCase()===family.name.toLowerCase() && i.child===peer && i.status==='pending')) {
        if (previous) { previous.status='pending'; previous.message='Review this connection to enable calls both ways.'; }
        else data.invites.push({id:`review-${family.id}-${index}`,family:family.name,guardian:family.guardian,child:peer,direction:'incoming',status:'pending',message:'Review this connection to enable calls both ways.',date:'Today'});
      }
    }
    delete family.incoming;
    delete family.outgoing;
  }
  return data;
}
function syncConnectionRequests(family) {
  for (const invite of state.invites.filter(i=>i.direction==='outgoing' && i.status==='pending' && i.peers?.length && i.family.toLowerCase()===family.name.toLowerCase())) {
    const connections = family.connections.filter(c=>c.requestId===invite.id);
    const pending = connections.filter(c=>c.status==='pending');
    if (pending.length) invite.childIds=[...new Set(pending.map(c=>c.childId))];
    else invite.status=connections.some(c=>c.status==='approved')?'accepted':'cancelled';
  }
}
const STORAGE_KEY = 'frontporch-design-v1';
const seed = () => ({
  family: 'Maple', setupDismissed:false, parent: 'Morgan', email: 'morgan@example.com', contactExtensions:{'+12025550142':'6100','+12025550163':'6101'}, directoryListed: false, inviteCode: 'MAPLE-9Q4T', guardians: [], guardianInvites: [],
  children: [
    {id:'casey',name:'Casey',color:'yellow',phone:'Bedroom phone',extension:'4754',phoneStatus:'ready',quiet:true,start:'16:00',end:'17:00',days:'Weekdays',shortcuts:[{id:'casey-alex',digits:'2',target:'["family","river","Alex"]',label:'Alex',active:true}]},
    {id:'jordan',name:'Jordan',color:'blue',phone:'',extension:'',phoneStatus:'none',quiet:false,start:'16:00',end:'17:00',days:'Weekdays',shortcuts:[]},
  ],
  families: [{id:'river',name:'River',guardian:'Taylor',color:'lavender',peers:['Alex'],connections:[{childId:'casey',peer:'Alex',status:'approved'}]}],
  invites: [
    {id:'cedar-invite',family:'Cedar',guardian:'Sam',child:'Robin',direction:'incoming',status:'pending',message:'Robin would love to call your family after school.',date:'Today'},
    {id:'ash-invite',family:'Ash',guardian:'Avery',childIds:['casey'],direction:'outgoing',status:'pending',message:'Let’s stay in touch!',date:'Yesterday'},
  ],
  contacts: [{id:'grandma',name:'Grandma June',phone:'+12025550142',relation:'Grandparent',color:'peach',extension:'6100'},{id:'dad',name:'Drew’s mobile',phone:'+12025550163',relation:'Parent',color:'green',extension:'6101'}],
  activity: [{text:'You approved Casey’s connection with the River family.',time:'Yesterday'},{text:'You added Grandma June to your private contacts.',time:'Yesterday'}],
});
let state = seed();
try { const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY)); if ([1,2,3,4,5,6].includes(saved?.version) && saved.data?.children) state = migrateDemo(saved.data); } catch { /* A fresh demo is always available. */ }
const uid = () => globalThis.crypto?.randomUUID?.() || `demo-${Date.now()}-${Math.random().toString(36).slice(2)}`;
const childById = id => state.children.find(c => c.id === id);
const names = ids => ids.map(id => childById(id)?.name).filter(Boolean).join(', ');
const avatar = (name,color='blue',size='') => `<span class="avatar ${esc(color)} ${size}">${esc(name.slice(0,1).toUpperCase())}</span>`;
const pendingCount = () => state.invites.filter(i=>i.direction==='incoming'&&i.status==='pending').length;
const actionButton = (label,action,id='',kind='secondary',symbol='') => `<button type="button" class="button ${kind}" data-action="${action}"${id ? ` data-id="${esc(id)}"` : ''}>${symbol ? icon(symbol) : ''}${label}</button>`;
const emptyState = (symbol,title,copy,label,action) => `<div class="empty-state">${icon(symbol)}<h3>${title}</h3><p>${copy}</p>${label?actionButton(label,action,'','','plus'):''}</div>`;
function save(message) { if (message) state.activity.unshift({text:message,time:'Just now'}); state.activity=state.activity.slice(0,12); try { sessionStorage.setItem(STORAGE_KEY,JSON.stringify({version:6,data:state})); } catch { toast('Changes last until this page is refreshed.'); } }
let toastTimer;
function toast(message) { clearTimeout(toastTimer); $('#toast').textContent=message; $('#toast').classList.add('visible'); toastTimer=setTimeout(()=>$('#toast').classList.remove('visible'),4200); }
function go(destination='overview') {
  const next = destination === 'landing' ? '#welcome' : `#family/${destination}`;
  if (location.hash===next) { route(); } else location.hash=next;
}
function route() { const routeName=location.hash.split('/')[1]; screen=location.hash.startsWith('#family')?'family':'landing'; section=['overview','children','circle','directory','invites','contacts','settings'].includes(routeName)?routeName:'overview'; closeDialog(); render(); if(location.hash==='#how-it-works') $('#how-it-works')?.scrollIntoView(); else window.scrollTo(0,0); }
function render() { $('#app').innerHTML=screen==='landing'?landing():familyPage(); document.title=screen==='landing'?'FrontPorch · A little more hello':`${state.family} family · FrontPorch`; }
function familyPage() {
  const navs=[['overview','home','Overview'],['children','users','Children & phones'],['circle','leaf','Family connections'],['directory','search','Family directory'],['invites','mail','Invitations'],['contacts','book','External contacts']];
  const titles={overview:`The ${esc(state.family)} family`,children:'Their people. Their phones.',circle:'A circle you choose.',directory:'Find a familiar family.',invites:'A hello worth opening.',contacts:'Familiar voices, near and far.',settings:'Make yourself at home.'};
  const subtitles={overview:'A little independence for them. Peace of mind for you.',children:'Give each child a place to call their own.',circle:'Build connections with families you already know.',directory:'Explore families who have chosen to be listed in your private network.',invites:'Review who wants to connect, and keep track of your invitations.',contacts:'A private address book for the people outside FrontPorch.',settings:'Your family details and the parents who keep things running.'};
  const pageActions={overview:actionButton('Add a child','child','','','plus'),children:actionButton('Add a child','child','','','plus'),circle:actionButton('Connect a family','directory','','','plus'),directory:actionButton('Use an invite code','use-invite-code','','secondary','mail'),invites:actionButton('Connect a family','directory','','','plus'),contacts:actionButton('Add a contact','contact','','','plus'),settings:''};
  return `<div class="app-shell"><aside class="sidebar">${brand()}<div class="family-switch">${avatar(state.family,'blue')}<div><strong>${esc(state.family)} family</strong><span>Your private space</span></div></div><div class="nav-label">YOUR FRONT PORCH</div><nav aria-label="Family navigation">${navs.map(([key,symbol,label])=>`<a href="#family/${key}" class="nav-item ${section===key?'active':''}" ${section===key?'aria-current="page"':''}>${icon(symbol)}<span>${label}</span>${key==='invites'&&pendingCount()?`<span class="nav-count">${pendingCount()}</span>`:''}</a>`).join('')}</nav><div class="sidebar-bottom"><div class="sidebar-note">${icon('shield')}<p>A small circle.<br>A world of connection.</p></div><a href="#family/settings" class="nav-item ${section==='settings'?'active':''}" ${section==='settings'?'aria-current="page"':''}>${icon('settings')} Family settings</a><div class="profile">${avatar(state.parent,'yellow','small-avatar')}<div><strong>${esc(state.parent)}</strong><span>Parent & guardian</span></div></div></div></aside>
  <div class="workspace"><header class="app-topbar"><span>My FrontPorch <span class="breadcrumb-slash">/</span> ${navs.find(n=>n[0]===section)?.[2]||'Family settings'}</span><div class="topbar-right"><span class="privacy-label">${icon('lock')} ${section==='directory'?'Parents in your network':'Only your family'}</span><button class="icon-button notification-button" data-action="inbox" aria-label="Invitations${pendingCount()?`, ${pendingCount()} waiting`:''}">${icon('mail')}${pendingCount()?'<span class="notification-dot"></span>':''}</button>${avatar(state.parent,'yellow','small-avatar')}<button type="button" class="icon-button" data-action="settings" aria-label="Family settings">${icon('settings')}</button><button type="button" class="logout-button" data-action="logout">${icon('logout')}<span>Log out</span></button></div></header>
  <main id="main" class="family-main" tabindex="-1"><div class="page-heading"><div><div class="eyebrow">${section==='overview'?`WELCOME HOME, ${esc(state.parent.toUpperCase())}`:section==='directory'?'YOUR PRIVATE NETWORK':'YOUR FAMILY’S FRONT PORCH'}</div><h1>${titles[section]}</h1><p>${subtitles[section]}</p></div>${pageActions[section]}</div>${({overview:overview,children:childrenPage,circle:circlePage,directory:directoryPage,invites:invitesPage,contacts:contactsPage,settings:settingsPage}[section])()}</main><footer class="app-footer"><span>${icon('shield')} Private by design. Connected by choice.</span><span>Emergency calling is not available.</span></footer></div></div>`;
}
function setupChecklist() {
  if(state.setupDismissed)return '';
  const phoneDone=state.children.length>0&&state.children.every(c=>c.extension); const circleDone=state.families.some(f=>f.connections.some(c=>c.status==='approved'));const count=1+Number(phoneDone)+Number(circleDone);
  return `<section class="setup-banner" aria-label="Family setup checklist"><div class="setup-banner-intro"><span class="setup-icon">${icon('home')}</span><div class="setup-copy"><h2>${count===3?'Your front porch is taking shape.':'A few little steps. A lot of connection.'}</h2><p>${count===3?'Keep your family’s phones and trusted circle up to date.':'Let’s get your family ready for their first hello.'}</p></div><div class="setup-controls"><span class="setup-count">${count} of 3 complete</span><button type="button" class="text-button setup-dismiss" data-action="dismiss-setup">${icon('close')} Dismiss setup</button></div></div><div class="setup-steps"><button data-action="settings"><span class="step-number done">${icon('check')}</span><span>Make it your family<strong>${esc(state.family)} family is set up</strong></span></button><button data-action="children"><span class="step-number ${phoneDone?'done':''}">${phoneDone?icon('check'):'2'}</span><span>Add their phones<strong>${phoneDone?'A phone for every child':'Give each child a place to call'}</strong></span>${icon('chevron')}</button><button data-action="circle"><span class="step-number ${circleDone?'done':''}">${circleDone?icon('check'):'3'}</span><span>Build your circle<strong>${circleDone?'Your first connection is here':'Invite a family you know'}</strong></span>${icon('chevron')}</button></div></section>`;
}
function childCard(child) {
  const families=state.families.filter(f=>f.connections.some(c=>c.childId===child.id&&c.status==='approved')).length;
  const contacts=state.contacts.length;
  return `<article class="child-card"><div class="child-card-heading">${avatar(child.name,child.color)}<div><h3>${esc(child.name)}</h3><span>${child.phone?esc(child.phone):'A phone of their own'}</span></div><button class="icon-button" data-action="child" data-id="${child.id}" aria-label="Edit ${esc(child.name)}">${icon('edit')}</button></div><div class="phone-status"><span>${icon('phone')}${child.extension?`Extension <b>${esc(child.extension)}</b>`:'No phone registered yet'}</span><span class="pill ${child.phoneStatus==='ready'?'green':child.extension?'blue':'amber'}">${child.phoneStatus==='ready'?'Ready to call':child.extension?'Setup pending':'Needs setup'}</span></div><div class="child-meta"><span>${icon('users')} ${families} ${families===1?'family':'families'} · ${contacts} external ${contacts===1?'contact':'contacts'}</span><span>${icon('clock')} ${child.quiet?`${esc(child.days)} · ${formatTime(child.start)}–${formatTime(child.end)}`:'No quiet hours set'}</span>${child.extension?`<button type="button" class="shortcut-card-link" data-action="shortcuts" data-id="${child.id}">${icon('phone')} Dial shortcuts <span>${(child.shortcuts||[]).length} set ${icon('chevron')}</span></button>`:''}</div><button class="card-action" data-action="${child.extension?'child-detail':'phone'}" data-id="${child.id}">${child.extension?'Manage phone & permissions':'Set up their phone'} ${icon('arrow')}</button></article>`;
}
function overview() {
  const inbox=state.invites.filter(i=>i.direction==='incoming'&&i.status==='pending');
  return `${setupChecklist()}<div class="dashboard-grid"><div class="dashboard-primary"><section><div class="section-heading"><h2>Children & phones <span class="heading-count">${state.children.length}</span></h2><button class="text-button blue-text" data-action="children">View all ${icon('arrow')}</button></div><div class="children-grid">${state.children.length?state.children.map(childCard).join(''):emptyState('users','Their first hello starts here.','Add a child, then register their phone.','Add your first child','child')}</div></section><section class="connections-preview"><div class="section-heading"><h2>Your family connections</h2><button class="text-button blue-text" data-action="circle">Manage ${icon('arrow')}</button></div><div class="panel compact">${state.families.length?state.families.map(f=>familyRow(f)).join(''):emptyState('leaf','Good company starts with an invitation.','Connect with a family you already know.','Browse the directory','directory')}<button class="subtle-add" data-action="directory">${icon('plus')} Find another family</button></div></section><section class="activity-section"><div class="section-heading"><h2>Around your front porch</h2><span class="muted">Recent changes</span></div>${state.activity.length?state.activity.slice(0,3).map(a=>`<div class="activity-row"><span class="activity-icon">${icon('check')}</span><p>${esc(a.text)}</p><time>${esc(a.time)}</time></div>`).join(''):'<p class="muted">Your family’s updates will appear here.</p>'}</section></div><aside class="dashboard-secondary"><section class="inbox-panel"><div class="section-heading"><h2>${icon('mail')} A little hello</h2>${inbox.length?`<span class="nav-count">${inbox.length}</span>`:''}</div>${inbox.length?inbox.slice(0,2).map(i=>`<div class="invite-peek"><div class="person-line">${avatar(i.family,'lavender','small-avatar')}<div><h3>The ${esc(i.family)} family</h3><span>${esc(i.guardian)} sent an invitation</span></div></div><p>${esc(i.child)} would like to connect with your children for calls both ways.</p><button class="button full-width" data-action="review-invite" data-id="${i.id}">Review invitation ${icon('arrow')}</button></div>`).join(''):'<div class="small-empty">You’re all caught up.<br>New invitations will appear here.</div>'}<button class="text-button" data-action="inbox">All invitations ${icon('chevron')}</button></section><section class="trust-note"><div class="note-symbol">${icon('shield')}</div><h3>Their freedom.<br>Your boundaries.</h3><p>Only approved people can reach your family. Every new connection starts with a parent’s say-so.</p><a href="#family/circle">See your family’s connections ${icon('arrow')}</a></section><div class="external-peek"><span class="icon-tile">${icon('book')}</span><h3>Grandparents count, too.</h3><p>Keep trusted people outside FrontPorch a phone call away.</p><button class="text-button blue-text" data-action="contacts">Manage external contacts ${icon('arrow')}</button></div></aside></div>`;
}
function childrenPage() { return `<div class="info-strip">${icon('shield')}<p>New children share your family’s saved external contacts. Connections with other FrontPorch families still need approval for each child.</p></div><div class="children-grid expanded">${state.children.length?state.children.map(childCard).join(''):emptyState('users','A place for each child.','Start with a first name. You can add their phone next.','Add a child','child')}</div><div class="section-footnote">${icon('info')} A registered phone still needs to be connected and verified before it can make calls.</div>`; }
function familyRow(f) {
  const approved=f.connections.filter(c=>c.status==='approved');
  return `<div class="family-row">${avatar(f.name,f.color)}<div class="family-row-copy"><h3>The ${esc(f.name)} family</h3><p>${esc(f.guardian)} · ${approved.length} two-way ${approved.length===1?'connection':'connections'}</p></div><span class="pill ${approved.length?'green':'amber'}">${approved.length?'Connected':f.connections.length?'Awaiting approval':'No active connections'}</span><button class="icon-button" data-action="family-detail" data-id="f-${f.id}" aria-label="Manage ${esc(f.name)} family connection">${icon('chevron')}</button></div>`;
}
function circlePage() {
  return `<div class="info-strip">${icon('shield')}<p>One invitation, one acceptance. The children included can call each other both ways. You can remove a connection at any time.</p></div><div class="connection-grid">${state.families.length?state.families.map(f=>`<article class="connection-card"><div class="person-line">${avatar(f.name,f.color)}<div><h2>The ${esc(f.name)} family</h2><span>${esc(f.guardian)} · Parent & guardian</span></div></div><div class="direction-block"><div class="mini-label">CHILDREN CONNECTED</div>${f.connections.length?f.connections.map(c=>`<div class="permission-line"><span>${esc(childById(c.childId)?.name||'Child')} ↔ ${esc(c.peer)}</span><span class="pill ${c.status==='approved'?'green':'amber'}">${c.status==='approved'?'Two-way calling':'Awaiting approval'}</span></div>`).join(''):'<p class="muted">No children connected yet.</p>'}</div><button class="card-action" data-action="family-detail" data-id="f-${f.id}">Manage connection ${icon('arrow')}</button></article>`).join(''):emptyState('leaf','Start with someone you know.','Explore families who have opted into the directory, or use a code shared by a parent.','Browse the directory','directory')}</div>`;
}
let inviteTab='incoming';

function invitesPage() { const items=state.invites.filter(i=>inviteTab==='history'?i.status!=='pending':i.direction===inviteTab&&i.status==='pending');return `<div class="tab-list" role="tablist" aria-label="Invitation type">${[['incoming','Received'],['outgoing','Sent'],['history','History']].map(([key,label])=>`<button role="tab" id="tab-${key}" aria-selected="${inviteTab===key}" aria-controls="invite-panel" tabindex="${inviteTab===key?'0':'-1'}" data-action="invite-tab" data-id="${key}" class="${inviteTab===key?'selected':''}">${label}<span>${state.invites.filter(i=>key==='history'?i.status!=='pending':i.direction===key&&i.status==='pending').length}</span></button>`).join('')}</div><div id="invite-panel" role="tabpanel" aria-labelledby="tab-${inviteTab}" class="invite-list">${items.length?items.map(i=>`<article class="invite-card"><div class="invite-card-top"><div class="person-line">${avatar(i.family,'lavender')}<div><h2>The ${esc(i.family)} family</h2><span>${esc(i.guardian||'Family guardian')} · ${esc(i.date)}</span></div></div><span class="pill ${i.status==='accepted'?'green':i.status==='pending'?'amber':'neutral'}">${i.status==='pending'?(i.direction==='incoming'?'Needs your approval':'Waiting for their approval'):esc(i.status[0].toUpperCase()+i.status.slice(1))}</span></div><p>${i.status==='accepted'&&i.reciprocal?`You connected <strong>${esc(names(i.acceptedChildIds))}</strong> with <strong>${esc(i.child)}</strong> for calls both ways.`:i.direction==='incoming'?`<strong>${esc(i.child)}</strong> would like to connect with your children for calls both ways.`:`You invited the ${esc(i.family)} family to connect with <strong>${esc(names(i.childIds))}</strong> for calls both ways.`}</p>${i.message?`<blockquote>“${esc(i.message)}”</blockquote>`:''}<div class="invite-card-bottom"><span>${icon('shield')} ${i.status==='pending'?'Calling stays off until both families approve.':i.status==='accepted'?'Accepted · manage current permissions in Family connections.':'This request does not allow calling.'}</span>${i.status==='pending'?(i.direction==='incoming'?`<div>${actionButton('Decline','decline-invite',i.id)}${actionButton('Review invitation','review-invite',i.id,'')}</div>`:actionButton('Cancel invitation','cancel-invite',i.id)):''}</div></article>`).join(''):emptyState('mail',inviteTab==='incoming'?'You’re all caught up.':inviteTab==='outgoing'?'No invitations waiting.':'A fresh start.','Your '+(inviteTab==='history'?'past invitations':'invitations')+' will appear here.',inviteTab==='outgoing'?'Browse the directory':'', 'directory')}</div>`; }
function contactsPage() {
  return `<section class="family-contacts-banner"><span class="icon-tile">${icon('users')}</span><div><h2>Familiar voices for the whole family.</h2><p>Adding a contact approves calls both ways with all your children, including children you add later.</p></div></section>${state.contacts.length?`<div class="contacts-table-wrap"><table class="contacts-table"><thead><tr><th scope="col">Contact</th><th scope="col">Dial extension</th><th scope="col">Calling access</th><th scope="col"><span class="sr-only">Manage</span></th></tr></thead><tbody>${state.contacts.map(c=>`<tr><th scope="row"><div class="person-line">${avatar(c.name,c.color,'small-avatar')}<div><strong>${esc(c.name)}</strong><span>${esc(c.relation)} · ${formatPhone(c.phone)}</span></div></div></th><td class="contact-extension-cell"><span class="contact-extension">${esc(c.extension)}</span><small class="contact-detail">Automatically assigned</small></td><td class="contact-access-cell"><span class="pill green">${icon('check')} All children</span><small class="contact-detail">Calls both ways</small></td><td class="contact-edit-cell"><button class="text-button blue-text" data-action="contact" data-id="${esc(c.id)}">Edit <span class="sr-only">${esc(c.name)}</span>${icon('chevron')}</button></td></tr>`).join('')}</tbody></table></div>`:emptyState('book','Keep a familiar voice close.','Add a trusted person to approve calling with every child in your family.','Add a contact','contact')}<div class="section-footnote">${icon('phone')} Dial a contact’s four-digit extension, or assign them a shortcut on each child’s phone.</div><div class="section-footnote">${icon('lock')} Contact names are private to your family. Removing a contact revokes this family approval for all children.</div>`;
}
function settingsPage() { return `<div class="settings-grid"><section class="panel settings-panel"><div class="section-heading"><h2>Your family</h2>${actionButton('Edit details','edit-family','','secondary','edit')}</div><div class="family-identity">${avatar(state.family,'blue')}<div><h3>${esc(state.family)} family</h3><p>Other parents see this name on your listing and invitations.</p></div></div><dl class="details-list"><div><dt>Family name</dt><dd>${esc(state.family)}</dd></div><div><dt>Primary guardian</dt><dd>${esc(state.parent)}</dd></div><div><dt>Email</dt><dd>${esc(state.email)}</dd></div></dl><button type="button" class="text-button blue-text" data-action="show-setup">${icon('home')} ${state.setupDismissed?'Show setup checklist':'View setup checklist'} ${icon('arrow')}</button></section>${guardiansPanel()}${directorySettings()}<section class="safety-panel"><span class="icon-tile">${icon('info')}</span><div><h3>Keep another phone for emergencies.</h3><p>FrontPorch does not support emergency calls. Your family needs another way to reach emergency services.</p></div></section></div>`; }
function formatTime(value) { const [h,m]=value.split(':').map(Number); return `${h%12||12}${m?':'+String(m).padStart(2,'0'):''}${h>=12?'pm':'am'}`; }
function formatPhone(value) { return /^\+1\d{10}$/.test(value)?`+1 (${value.slice(2,5)}) ${value.slice(5,8)}-${value.slice(8)}`:esc(value); }
function textField(label,name,value='',extra='') { return `<label class="field"><span>${label}</span><input name="${name}" value="${esc(value)}" ${extra}></label>`; }
function childChecks(name,selected=[]) { return state.children.length?`<div class="checkbox-list">${state.children.map(c=>`<label class="check-row"><input type="checkbox" name="${name}" value="${c.id}" ${selected.includes(c.id)?'checked':''}>${avatar(c.name,c.color,'tiny-avatar')}<span>${esc(c.name)}</span></label>`).join('')}</div>`:'<p class="form-note">Add a child before setting calling permissions.</p>'; }
let dialogReturnFocus;
function openDialog(title,content,{form='',submit='',eyebrow='',wide=false,extra='',cancelAction='close',cancelId=''}={}) {
  const dialog=$('#dialog'); if(dialog.open) dialog.close(); dialogReturnFocus=document.activeElement;
  dialog.classList.toggle('wide-dialog',wide);dialog.innerHTML=`<div class="dialog-heading"><div>${eyebrow?`<div class="eyebrow">${eyebrow}</div>`:''}<h2 id="dialog-title">${title}</h2></div><button class="icon-button" data-action="close" aria-label="Close dialog">${icon('close')}</button></div>${form?`<form data-form="${form}" ${extra}>`:''}<div class="dialog-body">${content}<p class="form-error" role="alert" hidden></p></div>${submit?`<div class="dialog-footer">${actionButton('Cancel',cancelAction,cancelId)}<button class="button" type="submit">${submit} ${icon('arrow')}</button></div>`:''}${form?'</form>':''}`;dialog.showModal();
}
function closeDialog(){ const d=$('#dialog');if(d.open){d.close();if(dialogReturnFocus?.isConnected)dialogReturnFocus.focus();} }
function formError(form,message) { const el=$('.form-error',form);el.hidden=false;el.textContent=message; }
function finish(message) { save(message);closeDialog();render();toast(message); }
function authDialog(mode) {
  const signup=mode==='signup';openDialog(signup?'A place for your family.':'Welcome back.',`<p class="dialog-intro">${signup?'Start with you. We’ll set up your family next.':'Log in to take care of your family’s little corner.'}</p><div class="demo-notice">Design preview: use fictional details. No account is created and passwords are not saved.</div>${signup?textField('Your first name','parent','','required maxlength="60" autocomplete="off" placeholder="e.g. Morgan"'):''}${textField('Email address','email',signup?'':'morgan@example.com','type="email" required autocomplete="off" placeholder="you@example.com"')}${textField('Password','password','','type="password" required autocomplete="off" placeholder="Any demo password"')}<p class="auth-switch">${signup?'Already have an account?':'New to FrontPorch?'} <button class="text-button blue-text" type="button" data-action="${signup?'login':'signup'}">${signup?'Log in':'Set up your family'}</button></p>`,{form:mode,submit:signup?'Continue':'Log in',eyebrow:'WELCOME TO FRONTPORCH'});
}
let signupDraft=null;
function setupFamilyDialog() {
  openDialog('What should we call your family?',`<p class="dialog-intro">A familiar name for your own little corner of FrontPorch.</p>${textField('Family name','family','','required maxlength="60" placeholder="e.g. Maple"')}<div class="signup-directory-choice"><label class="check-row"><input type="checkbox" name="directoryListed"><span>Let other parents in this network find our family</span></label><p class="form-note">Your family name and your name will appear in the parent directory. Your children’s details stay private. You can change this later.</p><div class="listing-preview"><span class="mini-label">YOUR LISTING PREVIEW</span><div class="person-line">${avatar('F','blue')}<div><h3 id="signup-listing-family">Your family</h3><span>${esc(signupDraft?.parent||'Your name')} · Parent & guardian</span></div></div></div></div><p class="form-note">Prefer to stay unlisted? You can still connect using your family’s invite code.</p>`,{form:'setup-family',submit:'Create your family',eyebrow:'FAMILY SETUP · 1 OF 3'});
}
function childDialog(id) { const c=childById(id);openDialog(c?`A little about ${esc(c.name)}.`:'Who’s picking up the phone?',`<p class="dialog-intro">Children don’t need accounts. You manage their phone and who they can call.</p>${textField('Child’s first name','name',c?.name||'','required maxlength="60" placeholder="e.g. Casey"')}<fieldset class="avatar-options"><legend>Choose a color</legend>${['yellow','blue','lavender','peach','green'].map(color=>`<label><input type="radio" name="color" value="${color}" ${(c?.color||'yellow')===color?'checked':''}><span class="avatar ${color}">${icon('users')}</span><span class="sr-only">${color}</span></label>`).join('')}</fieldset><div class="info-strip">${icon('shield')}<p>${c?'Calling permissions are managed separately.':'Saved family contacts are available to every child. Connections with other FrontPorch families need separate approval.'}</p></div>`,{form:'child',submit:c?'Save changes':'Add child',extra:`data-id="${id||''}"`}); }
function phoneDialog(id) { const c=childById(id); if(!c)return;openDialog(`${esc(c.name)}’s place to call.`,`<p class="dialog-intro">Register a phone for ${esc(c.name)}. We’ll keep the technical details tucked away.</p>${textField('Phone name','phone',c.phone||`${c.name}’s bedroom phone`,'required maxlength="80"')}<label class="field"><span>Extension</span><div class="input-with-action"><input name="extension" value="${esc(c.extension)}" required inputmode="numeric" pattern="[1-9][0-9]{3}" maxlength="4" placeholder="e.g. 5249" aria-describedby="extension-help"><button type="button" data-action="assign-extension">Assign one</button></div></label><p id="extension-help" class="form-note">A unique four-digit number for this phone. Use the number provided by your installer, or assign one in this demo.</p><div class="info-strip">${icon('info')}<p>Registration is the first step. Your installer will connect the physical phone and verify that it’s ready.</p></div>`,{form:'phone',submit:'Save phone',extra:`data-id="${id}"`}); }
function childDetail(id) {
  const c=childById(id);if(!c)return;const familyNames=state.families.flatMap(f=>f.connections.filter(c=>c.childId===id&&c.status==='approved').map(c=>`${c.peer} · ${f.name} family`));const contactNames=state.contacts.map(t=>t.name);
  openDialog(`${esc(c.name)}’s phone & permissions`,`<div class="child-detail-identity">${avatar(c.name,c.color)}<div><h3>${esc(c.phone)}</h3><p>Extension ${esc(c.extension)} · ${c.phoneStatus==='ready'?'Ready to call':'Awaiting phone connection'}</p></div><button class="text-button blue-text" data-action="phone" data-id="${id}">Edit</button></div><div class="detail-section"><h3>Who ${esc(c.name)} can call</h3><div class="permission-line"><span>Your family’s phones</span><span class="pill green">Allowed</span></div>${familyNames.map(n=>`<div class="permission-line"><span>${esc(n)}</span><span class="pill green">Two-way calling</span></div>`).join('')}${contactNames.map(n=>`<div class="permission-line"><span>${esc(n)}</span><span class="pill green">Family contact · two-way</span></div>`).join('')}<p class="form-note">Everyone else is blocked. New connections need your approval.</p><div class="inline-actions"><button class="text-button blue-text" data-action="circle">Family connections ${icon('arrow')}</button><button class="text-button blue-text" data-action="contacts">External contacts ${icon('arrow')}</button></div></div><div class="detail-section shortcut-overview"><div><h3>Dial shortcuts</h3><p class="form-note">${(c.shortcuts||[]).length} of 9 keys assigned. A single digit for a familiar voice.</p></div>${actionButton('Manage shortcuts','shortcuts',id,'secondary','phone')}</div><div class="detail-section"><h3>Quiet hours</h3><p class="form-note">Pause ${esc(c.name)}’s calls during homework or other time away from the phone.</p><label class="check-row"><input type="checkbox" name="quiet" ${c.quiet?'checked':''}> Use quiet hours</label><div class="form-row"><label class="field"><span>Days</span><select name="days">${['Weekdays','Weekends','Every day'].map(d=>`<option ${d===c.days?'selected':''}>${d}</option>`).join('')}</select></label>${textField('From','start',c.start,'type="time" required')}${textField('Until','end',c.end,'type="time" required')}</div><p class="form-note">Times use this device’s local time zone: ${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}.</p></div>`,{form:'quiet',submit:'Save quiet hours',extra:`data-id="${id}"`});
}
// Each demo child has one phone; production shortcuts belong to a Device.
function shortcutTargets(childId) {
  if (!childById(childId)?.extension) return [];
  return [
    ...state.children.filter(c=>c.id!==childId&&c.extension).map(c=>({key:JSON.stringify(['home',c.id]),name:c.name,detail:`${c.phone} · ${c.extension}`,group:'Your family’s phones'})),
    ...state.families.flatMap(f=>f.connections.filter(c=>c.childId===childId&&c.status==='approved').map(c=>({key:JSON.stringify(['family',f.id,c.peer]),name:c.peer,detail:`${f.name} family`,group:'Approved family connections'}))),
    ...state.contacts.map(c=>({key:JSON.stringify(['contact',c.phone]),name:c.name,detail:`Extension ${c.extension}`,group:'Family contacts'})),
  ];
}
function shortcutStatus(childId,shortcut) {
  const target=shortcutTargets(childId).find(t=>t.key===shortcut.target);
  if(target)return {target,available:true,text:shortcut.active?'Enabled':'Paused'};
  let reason='Calling permission removed';
  try {
    const [kind,id]=JSON.parse(shortcut.target);
    if(kind==='contact') {
      const contact=state.contacts.find(c=>c.phone===id);
      reason=contact?'Phone no longer available':'Number no longer in family contacts';
    } else if(kind==='home') reason='Phone no longer available';
  } catch { reason='Destination unavailable'; }
  return {available:false,text:reason};
}
function shortcutsDialog(id) {
  const child=childById(id);if(!child)return;
  if(!child.extension){openDialog('A phone comes first.',`<p class="dialog-intro">Register ${esc(child.name)}’s phone, then choose the people each shortcut will call.</p>${actionButton('Set up their phone','phone',id,'','phone')}`);return;}
  const shortcuts=child.shortcuts||[];
  openDialog(`${esc(child.name)}’s dial shortcuts.`,`<div class="shortcut-phone"><span class="icon-tile">${icon('phone')}</span><div><strong>${esc(child.phone)}</strong><span>Extension ${esc(child.extension)} · ${shortcuts.length} of 9 keys assigned</span></div></div><p class="dialog-intro">Pick up the phone and dial one digit to call someone familiar. These keys are just for ${esc(child.name)}’s phone.</p><div class="shortcut-grid">${Array.from({length:9},(_,i)=>String(i+1)).map(digits=>{
    const shortcut=shortcuts.find(s=>s.digits===digits);const status=shortcut?shortcutStatus(id,shortcut):null;
    return `<button type="button" class="shortcut-slot ${shortcut?'assigned':'empty-slot'} ${status&&!status.available?'unavailable':''}" data-action="edit-shortcut" data-id="${esc(id)}" data-digits="${digits}" aria-label="${esc(shortcut?`Edit dial ${digits}: ${shortcut.label||status.target?.name||shortcut.targetName||'Saved contact'}`:`Assign dial ${digits}`)}"><span class="shortcut-digit">${digits}</span><span class="shortcut-slot-copy"><strong>${shortcut?esc(shortcut.label||status.target?.name||shortcut.targetName||'Saved contact'):'Assign a person'}</strong><small>${shortcut?esc(status.target?`${status.target.name} · ${status.target.detail}`:'Choose another approved person'):'Not assigned'}</small>${shortcut?`<span class="shortcut-state ${status.available&&shortcut.active?'enabled':''}">${esc(status.text)}</span>`:''}</span>${icon(shortcut?'edit':'plus')}</button>`;
  }).join('')}</div><div class="info-strip">${icon('shield')}<p>Shortcuts keep the same calling permissions and quiet hours. They never approve a new connection.</p></div><p class="form-note">Use keys 1–9. You can use the same key for different people on different phones.</p><div class="inline-actions">${actionButton('Back to phone','child-detail',id,'text-button blue-text')}${actionButton('Done','close','','')}</div>`,{wide:true,eyebrow:'A FAMILIAR VOICE, ONE DIGIT AWAY'});
}
function shortcutEditDialog(childId,digits) {
  const child=childById(childId);if(!child?.extension||!/[1-9]/.test(digits)||digits.length!==1)return;
  const shortcut=(child.shortcuts||[]).find(s=>s.digits===digits);
  const targets=shortcutTargets(childId);const status=shortcut?shortcutStatus(childId,shortcut):null;
  if(!targets.length&&!shortcut){openDialog('Choose their people first.',`<p class="dialog-intro">There isn’t an approved phone or contact to assign yet. Connect with a family, register another phone at home, or add a family contact.</p><div class="guardian-complete-actions">${actionButton('Back to shortcuts','shortcuts',childId)}${actionButton('Family connections','circle','','')}</div>`);return;}
  openDialog(shortcut?`Edit ${esc(child.name)}’s shortcut.`:`A shortcut for ${esc(child.name)}.`,`<p class="dialog-intro">Choose what one digit does on ${esc(child.phone)} · ${esc(child.extension)}.</p><label class="field"><span>Dial key</span><select name="digits" required>${Array.from({length:9},(_,i)=>String(i+1)).map(key=>{const occupied=(child.shortcuts||[]).some(s=>s.digits===key&&s.id!==shortcut?.id);return `<option value="${key}" ${key===digits?'selected':''} ${occupied?'disabled':''}>${key}${occupied?' · Already assigned':''}</option>`;}).join('')}</select></label><label class="field"><span>Who should it call?</span><select name="target" required><option value="">Choose an approved person</option>${status&&!status.available?`<option value="${esc(shortcut.target)}" selected>${esc(shortcut.label||shortcut.targetName||'Saved contact')} · Unavailable</option>`:''}${[...new Set(targets.map(t=>t.group))].map(group=>`<optgroup label="${esc(group)}">${targets.filter(t=>t.group===group).map(t=>`<option value="${esc(t.key)}" ${shortcut?.target===t.key?'selected':''}>${esc(t.name)} · ${esc(t.detail)}</option>`).join('')}</optgroup>`).join('')}</select></label>${textField('Short name <small>(optional)</small>','label',shortcut?.label||'','maxlength="40" placeholder="e.g. Grandma"')}<p class="form-note">Leave this blank to use their name. This label is private to your family.</p><label class="check-row"><input type="checkbox" name="active" ${!shortcut||shortcut.active?'checked':''}> Shortcut enabled</label><p class="form-note">Pause a shortcut by turning this off. Their regular calling permission stays the same.</p>${status&&!status.available?`<div class="shortcut-warning">${icon('info')}<p>${esc(status.text)}. This shortcut cannot place calls. Choose an approved person, pause it, or remove it.</p></div>`:''}<div class="info-strip">${icon('shield')}<p>Only people ${esc(child.name)} can already call appear here. Saved family contacts are approved for every child.</p></div>${shortcut?`<button type="button" class="text-button danger-text" data-action="remove-shortcut" data-id="${esc(childId)}" data-shortcut="${esc(shortcut.id)}">Remove shortcut</button>`:''}`,{form:'shortcut',submit:'Save shortcut',extra:`data-id="${esc(childId)}" data-shortcut="${esc(shortcut?.id||'')}"`,cancelAction:'shortcuts',cancelId:childId});
}
function finishShortcut(childId,message) { finish(message);shortcutsDialog(childId); }
function inviteDialog(target=null,source='directory',code='') {
  if(!target){go('directory');return;}
  if(!state.children.length){openDialog('Add a child first.',`<p class="dialog-intro">Choose the children you’d like to include in a two-way family connection.</p>${actionButton('Add your first child','child','','','plus')}`);return;}
  inviteDraft={id:target.id,source,code};
  openDialog(`Connect with the ${esc(target.name)} family.`,`<div class="person-line invitation-family">${avatar(target.name,target.color)}<div><h3>The ${esc(target.name)} family</h3><span>${esc(target.guardians.join(' & '))} · Parents & guardians</span></div></div><p class="dialog-intro">Choose your children for this invitation. Calling starts after the other parent accepts.</p><fieldset><legend>Which of your children are included?</legend>${childChecks('children')}</fieldset><p class="form-note">Sending approves your side. The other parent chooses their children and accepts to complete the two-way connection.</p><label class="field"><span>A little hello <small>(optional)</small></span><textarea name="message" rows="3" maxlength="300" placeholder="A note to the other parent"></textarea></label><div class="demo-notice">Invitations stay in this local prototype. Nothing is sent to another family.</div>`,{form:'invite',submit:'Send invitation'});
}
function reviewInvite(id) {
  const i=state.invites.find(i=>i.id===id&&i.status==='pending'&&i.direction==='incoming');if(!i)return;
  if(!state.children.length){openDialog('Add a child to connect.',`<p class="dialog-intro">The ${esc(i.family)} family’s invitation will stay here while you add your first child.</p>${actionButton('Add a child','child','','','plus')}`);return;}
  openDialog(`A hello from the ${esc(i.family)} family.`,`<div class="person-line">${avatar(i.family,'lavender')}<div><h3>${esc(i.guardian)}</h3><span>Guardian in the ${esc(i.family)} family</span></div></div>${i.message?`<blockquote>“${esc(i.message)}”</blockquote>`:''}<div class="approval-summary"><div class="mini-label">A TWO-WAY CONNECTION</div><h3>${esc(i.child)} ↔ <span id="invitation-participants">${esc(names(state.children.map(c=>c.id)))}</span></h3><p>Accepting lets these children call each other both ways. ${esc(i.guardian)} has already approved their side.</p></div><details class="invitation-options"><summary>Change which of your children are included</summary><fieldset><legend>Children in your family</legend>${childChecks('children',state.children.map(c=>c.id))}</fieldset></details><p class="form-note">You can manage or remove these connections at any time.</p>`,{form:'approve-invite',submit:'Accept invitation',extra:`data-id="${id}"`});
}
function familyDetail(rawId) {
  const id=rawId.replace(/^f-/,'');const f=state.families.find(f=>f.id===id);if(!f)return;
  openDialog(`Your connection with ${esc(f.name)}.`,`<p class="dialog-intro">Each connection allows calls both ways. Choose which of your children connect with each child in the ${esc(f.name)} family.</p>${f.peers.map((peer,index)=>`<fieldset><legend>Connected with ${esc(peer)}</legend>${childChecks(`children-${index}`,f.connections.filter(c=>c.peer===peer).map(c=>c.childId))}</fieldset>`).join('')}<p class="form-note">Unchecking a child stops calls both ways. Any new connection waits for the other family’s approval.</p><button type="button" class="text-button danger-text" data-action="disconnect" data-id="${f.id}">Disconnect this family</button>`,{form:'family-permissions',submit:'Save connections',extra:`data-id="${f.id}"`});
}
function contactDialog(id) {
  const c=state.contacts.find(c=>c.id===id);
  openDialog(c?'A familiar voice.':'Who’s in your extended circle?',`<p class="dialog-intro">Save a trusted person’s number for the whole family. Their contact name stays private.</p>${textField('Contact name','name',c?.name||'','required maxlength="80" placeholder="e.g. Grandma June"')}<div class="form-row">${textField('Phone number','phone',c?.phone||'','required type="tel" placeholder="+1 202 555 0142"')}<label class="field"><span>Relationship</span><select name="relation">${['Grandparent','Parent','Relative','Family friend','Other'].map(r=>`<option ${c?.relation===r?'selected':''}>${r}</option>`).join('')}</select></label></div><p class="form-note">Use a country code for numbers outside the US or Canada.</p><div class="contact-dial-summary"><div><strong>Dial extension</strong><p>${c?'Assigned to this number. Changing the number also means updating any shortcuts to it.':'A four-digit extension is assigned automatically when you save.'}</p></div>${c?`<span class="contact-extension">${esc(c.extension)}</span>`:icon('phone')}</div><div class="contact-approval-summary">${icon('shield')}<div><h3>${c?'Saving keeps this contact approved for all children.':'Adding this contact approves calls for all children.'}</h3><p>Your children can call this number, and this contact can call your children through FrontPorch. Children you add later are included, too.</p></div></div>${c?`<button type="button" class="text-button danger-text" data-action="delete-contact" data-id="${esc(c.id)}">Remove contact for everyone</button>`:''}`,{form:'contact',submit:c?'Save contact':'Add contact',extra:`data-id="${esc(id||'')}"`});
}
function confirmDialog(title,copy,action,id='',name='') {openDialog(title,`<p class="dialog-intro">${copy}</p><div class="confirm-actions">${actionButton('Keep as is','close')}<button class="button danger" data-action="${action}" data-id="${esc(id)}" data-name="${esc(name)}">Confirm</button></div>`);}
document.addEventListener('click', event=>{
  if(event.target.closest('.skip-link')){event.preventDefault();const main=$('#main');main.setAttribute('tabindex','-1');main.focus();main.scrollIntoView();return;}
  const el=event.target.closest('[data-action]');if(!el)return;event.preventDefault();const {action,id,name}=el.dataset;
  if(['overview','children','circle','directory','contacts','settings'].includes(action)){go(action);return;}
  switch(action){
    case 'landing': case 'logout':go('landing');break;
    case 'demo':go('overview');break;
    case 'dismiss-setup':state.setupDismissed=true;save();render();$('#main')?.focus();toast('Setup dismissed. You can reopen it in Family settings.');break;
    case 'show-setup':state.setupDismissed=false;save();go('overview');break;
    case 'login':case 'signup':authDialog(action);break;
    case 'close':closeDialog();break;
    case 'inbox':go('invites');break;
    case 'child':childDialog(id);break;
    case 'phone':phoneDialog(id);break;
    case 'child-detail':childDetail(id);break;
    case 'shortcuts':shortcutsDialog(id);break;
    case 'edit-shortcut':shortcutEditDialog(id,el.dataset.digits||'');break;
    case 'remove-shortcut':{
      const child=childById(id),shortcut=child?.shortcuts?.find(s=>s.id===el.dataset.shortcut);if(!shortcut)break;
      openDialog(`Remove dial ${esc(shortcut.digits)}?`,`<p class="dialog-intro">This frees up key ${esc(shortcut.digits)} on ${esc(child.name)}’s phone. It does not change who they are allowed to call.</p><div class="confirm-actions"><button type="button" class="button secondary" data-action="edit-shortcut" data-id="${esc(id)}" data-digits="${esc(shortcut.digits)}">Keep shortcut</button><button type="button" class="button danger" data-action="confirm-remove-shortcut" data-id="${esc(id)}" data-shortcut="${esc(shortcut.id)}">Remove shortcut</button></div>`);break;
    }
    case 'confirm-remove-shortcut':{
      const child=childById(id),shortcut=child?.shortcuts?.find(s=>s.id===el.dataset.shortcut);if(!shortcut)break;
      child.shortcuts=child.shortcuts.filter(s=>s.id!==shortcut.id);finishShortcut(id,`Dial ${shortcut.digits} removed from ${child.name}’s phone.`);break;
    }
    case 'invite':go('directory');break;
    case 'directory-invite':{const target=NETWORK_FAMILIES.find(f=>f.id===id&&f.listed&&!sameFamily(f.name,state.family));if(target)inviteDialog(target);break;}
    case 'directory-received':reviewInvite(id);break;
    case 'directory-sent':inviteTab='outgoing';go('invites');break;
    case 'use-invite-code':inviteCodeDialog();break;
    case 'share-invite-code':shareInviteCode();break;
    case 'copy-invite-code':copyInviteCode();break;
    case 'directory-visibility':state.directoryListed=!state.directoryListed;finish(state.directoryListed?'Your family is now listed in the parent directory.':'Your family is now hidden from the directory. Existing connections are unchanged.');$('[data-action="directory-visibility"]')?.focus();break;
    case 'clear-directory-search':directoryQuery='';$('#directory-search').value='';updateDirectoryResults();$('#directory-search').focus();break;
    case 'review-invite':reviewInvite(id);break;
    case 'family-detail':familyDetail(id);break;
    case 'contact':contactDialog(id);break;
    case 'invite-tab':inviteTab=id;render();$(`#tab-${id}`)?.focus();break;
    case 'assign-extension':{const extension=nextDemoExtension(state,5249);if(extension)$('[name="extension"]',$('#dialog')).value=extension;else toast('No free extensions are available in this demo.');break;}
    case 'decline-invite':confirmDialog('Decline this invitation?','This invitation will not connect the children in either direction. It will move to your history.','confirm-decline',id);break;
    case 'cancel-invite':confirmDialog('Cancel this invitation?','The request will be withdrawn. It will not grant any calling permissions.','confirm-cancel',id);break;
    case 'confirm-decline':case 'confirm-cancel':{const i=state.invites.find(i=>i.id===id);if(i&&i.status==='pending'){i.status=action==='confirm-decline'?'declined':'cancelled';if(i.direction==='outgoing'){const f=state.families.find(f=>f.name.toLowerCase()===i.family.toLowerCase());if(f)f.connections=f.connections.filter(c=>c.status!=='pending'||c.requestId!==i.id);}finish(`Invitation ${i.status}.`);}break;}
    case 'delete-contact':confirmDialog('Remove this contact?','This removes the contact’s calling approval for every child in your family. Saved shortcuts to this contact will become unavailable.','confirm-delete-contact',id);break;
    case 'confirm-delete-contact':state.contacts=state.contacts.filter(c=>c.id!==id);finish('Contact removed for all children. Shortcuts to this contact are now unavailable.');break;
    case 'disconnect':confirmDialog('Disconnect this family?','All calling approvals with this family will be revoked in both directions.','confirm-disconnect',id);break;
    case 'confirm-disconnect':{const f=state.families.find(f=>f.id===id);if(!f)break;state.invites.forEach(i=>{if(i.family.toLowerCase()===f.name.toLowerCase()&&i.status==='pending')i.status='cancelled';});state.families=state.families.filter(f=>f.id!==id);finish(`Disconnected from the ${f.name} family.`);break;}
    case 'invite-guardian':inviteGuardianDialog();break;
    case 'preview-guardian-invite':guardianJoinDialog(id);break;
    case 'guardian-join-mode':guardianJoinDialog(id,el.dataset.mode);break;
    case 'resend-guardian-invite':resendGuardianInvite(id);break;
    case 'cancel-guardian-invite':{const invitation=state.guardianInvites.find(i=>i.id===id);if(invitation&&guardianInviteStatus(invitation)==='pending')confirmDialog('Cancel this guardian invitation?',`${esc(invitation.name)} will no longer be able to use this invitation to join your family.`,'confirm-cancel-guardian',id);break;}
    case 'confirm-cancel-guardian':{const invitation=state.guardianInvites.find(i=>i.id===id);if(invitation&&guardianInviteStatus(invitation)==='pending'){invitation.status='cancelled';finish(`Guardian invitation for ${invitation.name} cancelled.`);}break;}
    case 'remove-guardian':{const guardian=state.guardians.find(g=>g.id===id);if(guardian)confirmDialog(`Remove ${esc(guardian.name)} as a guardian?`,'They will lose access to your family’s children, phones, contacts, and settings. Existing calling permissions will stay in place.','confirm-remove-guardian',id);break;}
    case 'confirm-remove-guardian':{const guardian=state.guardians.find(g=>g.id===id);if(guardian){state.guardians=state.guardians.filter(g=>g.id!==id);finish(`${guardian.name} no longer has guardian access.`);}break;}
    case 'edit-family':openDialog('Your family details.',`${textField('Family name','family',state.family,'required maxlength="60"')}${textField('Your first name','parent',state.parent,'required maxlength="60"')}${textField('Email address','email',state.email,'required type="email"')}`,{form:'edit-family',submit:'Save changes'});break;
    case 'reset':confirmDialog('Start fresh with the Maple family?','This resets your local demo changes and restores the sample children, connections, and invitations.','confirm-reset');break;
    case 'confirm-reset':state=seed();save();closeDialog();go('overview');toast('The sample family is ready to explore again.');break;
  }
});
document.addEventListener('submit',event=>{
  const form=event.target.closest('[data-form]');if(!form)return;event.preventDefault();const data=new FormData(form);const val=key=>String(data.get(key)||'').trim();const selected=key=>data.getAll(key).filter(id=>state.children.some(c=>c.id===id));const id=form.dataset.id;
  if([...form.querySelectorAll('input[required]:not([type="checkbox"])')].some(input=>!input.value.trim())){formError(form,'Please fill in all required fields.');return;}
  switch(form.dataset.form){
    case 'shortcut':{
      const child=childById(id);if(!child?.extension){formError(form,'Register this child’s phone first.');return;}
      const shortcutId=form.dataset.shortcut;const existing=(child.shortcuts||[]).find(s=>s.id===shortcutId);
      if(shortcutId&&!existing){formError(form,'This shortcut has been removed. Open shortcuts again to choose a free key.');return;}
      const digits=val('digits');if(!/^[1-9]$/.test(digits)){formError(form,'Choose a single digit from 1 to 9.');return;}
      if((child.shortcuts||[]).some(s=>s.digits===digits&&s.id!==existing?.id)){formError(form,'That key is already assigned on this phone. Choose a free key or edit its shortcut.');return;}
      const target=shortcutTargets(id).find(t=>t.key===val('target'));
      if(!target&&!(existing?.target===val('target')&&!data.has('active'))){formError(form,'Choose someone this child is currently allowed to call. To keep an unavailable shortcut, pause it.');return;}
      if(val('label').length>40){formError(form,'Use a short name of 40 characters or fewer.');return;}
      const shortcut={id:existing?.id||uid(),digits,target:val('target'),label:val('label'),targetName:target?.name||existing?.targetName||existing?.label||'Saved contact',active:data.has('active')};
      child.shortcuts=[...(child.shortcuts||[]).filter(s=>s.id!==shortcut.id),shortcut].sort((a,b)=>Number(a.digits)-Number(b.digits));
      finishShortcut(id,`${child.name}’s dial ${digits} shortcut ${shortcut.active?'saved':'paused'}.`);break;
    }
    case 'login':closeDialog();go('overview');toast('You’re exploring a local demo account.');break;
    case 'signup':signupDraft={parent:val('parent'),email:val('email')};form.reset();setupFamilyDialog();break;
    case 'setup-family':{state={...seed(),family:val('family'),parent:signupDraft?.parent||'Morgan',email:signupDraft?.email||'morgan@example.com',directoryListed:data.has('directoryListed'),inviteCode:`FP-${uid().replaceAll('-','').slice(0,8).toUpperCase()}`,children:[],families:[],invites:[],contacts:[],contactExtensions:{},activity:[]};signupDraft=null;save('Your family is set up. Welcome home!');closeDialog();go('overview');toast('Your family is set up. Add your first child next.');break;}
    case 'child':{if(state.children.some(c=>c.id!==id&&c.name.toLowerCase()===val('name').toLowerCase())){formError(form,'A child with this name is already in your family.');return;}const c=childById(id);if(c){c.name=val('name');c.color=val('color');finish('Child details updated.');}else{const created={id:uid(),name:val('name'),color:val('color'),phone:'',extension:'',phoneStatus:'none',quiet:false,start:'16:00',end:'17:00',days:'Weekdays',shortcuts:[]};state.children.push(created);finish(`${created.name} joined your family.`);phoneDialog(created.id);}break;}
    case 'phone':{if(Object.values(state.contactExtensions||{}).includes(val('extension'))){formError(form,'That extension belongs to a family contact. Choose another number.');return;}if(state.children.some(c=>c.id!==id&&c.extension===val('extension'))){formError(form,'That extension belongs to another child. Choose a different number.');return;}const c=childById(id);if(!c)return;const changed=c.extension!==val('extension');Object.assign(c,{phone:val('phone'),extension:val('extension'),phoneStatus:changed?'pending':c.phoneStatus});finish(`${c.name}’s phone details saved.${changed?' Phone connection is pending.':''}`);break;}
    case 'quiet':{if(data.has('quiet')&&val('start')>=val('end')){formError(form,'Choose an end time after the start time. For this draft, quiet hours must finish on the same day.');return;}const c=childById(id);if(!c)return;Object.assign(c,{quiet:data.has('quiet'),start:val('start'),end:val('end'),days:val('days')});finish(`${c.name}’s quiet hours updated.`);break;}
    case 'invite': {
      const target=resolveInviteDraft();
      if(!target){formError(form,'Choose a listed family or enter a valid invite code first.');return;}
      const childIds=[...new Set(selected('children'))];
      if(!childIds.length){formError(form,'Choose at least one child for this invitation.');return;}
      if(target.name.toLowerCase()===state.family.toLowerCase()){formError(form,'Choose a family outside your own.');return;}
      const incoming=state.invites.find(i=>i.direction==='incoming'&&i.status==='pending'&&sameFamily(i.family,target.name));
      if(incoming){formError(form,'This family has already invited you. Review their invitation in your inbox.');return;}
      const f=state.families.find(f=>sameFamily(f.name,target.name));
      const duplicates=childIds.some(cid=>f?.connections.some(c=>c.childId===cid)||state.invites.some(i=>i.direction==='outgoing'&&i.status==='pending'&&sameFamily(i.family,target.name)&&i.childIds.includes(cid)));
      if(duplicates){formError(form,'One of these children already has a connection or pending invitation. Choose only new children, or manage the existing connection.');return;}
      state.invites.push({id:uid(),family:target.name,guardian:target.guardians.join(' & '),childIds,direction:'outgoing',status:'pending',message:val('message'),date:'Just now'});
      if(f){const request=state.invites.at(-1);request.peers=[...f.peers];f.connections.push(...childIds.flatMap(childId=>f.peers.map(peer=>({childId,peer,status:'pending',requestId:request.id}))));}
      inviteDraft=null;finish(`Invitation to the ${target.name} family added to Sent. Nothing was sent outside this demo.`);inviteTab='outgoing';go('invites');break;
    }
    case 'invite-code': {
      const code=normalizeInviteCode(val('code'));
      if(code===normalizeInviteCode(state.inviteCode)){formError(form,'That is your own family’s code. Ask the other parent for theirs.');return;}
      const target=NETWORK_FAMILIES.find(f=>normalizeInviteCode(f.code)===code&&!sameFamily(f.name,state.family));
      if(!target){formError(form,'We couldn’t find that invite code. Check the code with the parent who shared it.');return;}
      inviteDialog(target,'code',code);break;
    }
    case 'approve-invite': {
      const i=state.invites.find(i=>i.id===id);
      if(!i||i.status!=='pending'||i.direction!=='incoming')return;
      const children=[...new Set(selected('children'))];
      if(!children.length){formError(form,'Include at least one child to accept this invitation.');return;}
      let f=state.families.find(f=>f.name.toLowerCase()===i.family.toLowerCase());
      if(!f){f={id:uid(),name:i.family,guardian:i.guardian,color:'lavender',peers:[],connections:[]};state.families.push(f);}
      if(!f.peers.includes(i.child))f.peers.push(i.child);
      for(const childId of children){
        const existing=f.connections.find(c=>c.childId===childId&&c.peer===i.child);
        if(existing)existing.status='approved';else f.connections.push({childId,peer:i.child,status:'approved'});
      }
      i.status='accepted';i.reciprocal=true;i.acceptedChildIds=children;
      syncConnectionRequests(f);
      finish(`${names(children)} and ${i.child} can now call each other both ways.`);
      break;
    }
    case 'family-permissions': {
      const f=state.families.find(f=>f.id===id);if(!f)return;
      const next=[];let added=0;
      for(const [index,peer] of f.peers.entries()){
        const children=[...new Set(selected(`children-${index}`))];
        const newChildren=children.filter(childId=>!f.connections.some(c=>c.childId===childId&&c.peer===peer));
        const requestId=uid();
        for(const childId of children)next.push(f.connections.find(c=>c.childId===childId&&c.peer===peer)||{childId,peer,status:'pending',requestId});
        if(newChildren.length){added+=newChildren.length;state.invites.push({id:requestId,family:f.name,guardian:f.guardian,childIds:newChildren,peers:[peer],direction:'outgoing',status:'pending',message:`Connect with ${peer} for calls both ways.`,date:'Just now'});}
      }
      f.connections=next;syncConnectionRequests(f);
      finish(added?'Connections saved. New connections are waiting for the other family’s approval.':'Two-way connections updated.');
      break;
    }
    case 'invite-guardian': {
      const name=val('name'),email=normalizeGuardianEmail(val('email'));
      if(!name||!validGuardianEmail(email)){formError(form,'Enter a name and a valid email address.');return;}
      if(guardianEmailTaken(email)){formError(form,'This email already belongs to a guardian in your family.');return;}
      if(state.guardianInvites.some(i=>normalizeGuardianEmail(i.email)===email&&guardianInviteStatus(i)==='pending')){formError(form,'An invitation is already waiting for this email. You can resend or cancel it in Family settings.');return;}
      if(guardianNameTaken(name)){formError(form,'Use a name that distinguishes this guardian from the others in your family.');return;}
      for(const old of state.guardianInvites.filter(i=>normalizeGuardianEmail(i.email)===email&&guardianInviteStatus(i)==='expired'))old.status='replaced';
      const invitation=newGuardianInvitation(name,email);
      state.guardianInvites.unshift(invitation);
      finish(`Guardian invitation for ${name} created in this demo.`);
      guardianInvitationCreated(invitation.id);break;
    }
    case 'join-as-guardian': {
      const invitation=state.guardianInvites.find(i=>i.id===id);
      if(!invitation||guardianInviteStatus(invitation)!=='pending'){formError(form,'This invitation is no longer available. Ask the primary guardian for a new one.');return;}
      if(normalizeGuardianEmail(val('email'))!==normalizeGuardianEmail(invitation.email)){formError(form,'Join using the email address this invitation was sent to.');return;}
      if(!val('name')||!val('password')){formError(form,'Enter your name and a demo password to continue.');return;}
      if(guardianEmailTaken(invitation.email)||guardianNameTaken(val('name'))){formError(form,'A guardian with this email or name is already in this family.');return;}
      state.guardians.push({id:uid(),name:val('name'),email:invitation.email,role:'guardian',joinedAt:Date.now()});
      invitation.status='accepted';invitation.acceptedAt=Date.now();
      form.reset();
      finish(`${val('name')||invitation.name} joined the ${state.family} family as a guardian.`);
      break;
    }
    case 'contact':{
      let number=val('phone').replace(/[\s().-]/g,'');
      if(/^\d{10}$/.test(number))number='+1'+number;else if(/^1\d{10}$/.test(number))number='+'+number;
      if(!/^\+[1-9]\d{7,14}$/.test(number)){formError(form,'Enter a phone number with country code, such as +1 202 555 0142.');return;}
      if(state.contacts.some(c=>c.id!==id&&c.phone===number)){formError(form,'This phone number is already in your family contacts. Edit the existing contact instead.');return;}
      const contact=state.contacts.find(c=>c.id===id);
      if(id&&!contact){formError(form,'This contact has been removed. Add it again to approve calling.');return;}
      const extension=contactExtension(state,number);
      if(!extension){formError(form,'No free extensions are available in this demo.');return;}
      const updated={name:val('name'),phone:number,relation:val('relation'),extension};
      if(contact)Object.assign(contact,updated);else state.contacts.push({...updated,id:uid(),color:'peach'});
      finish(`${updated.name} is approved for calls both ways with all your children. Dial ${extension} or set a shortcut.`);break;
    }
    case 'edit-family':if(state.guardians.some(g=>normalizeGuardianEmail(g.email)===normalizeGuardianEmail(val('email'))||g.name.trim().toLocaleLowerCase()===val('parent').toLocaleLowerCase())){formError(form,'That name or email already belongs to another guardian in your family.');return;}state.family=val('family');state.parent=val('parent');state.email=val('email');finish('Your family details are up to date.');break;
  }
});
document.addEventListener('input',event=>{
  if(event.target.id==='directory-search'){directoryQuery=event.target.value;updateDirectoryResults();}
  if(event.target.name==='family'&&event.target.closest('[data-form="setup-family"]'))$('#signup-listing-family').textContent=event.target.value.trim()?`${event.target.value.trim()} family`:'Your family';
});
document.addEventListener('change',event=>{
  const form=event.target.closest('[data-form="approve-invite"]');
  if(!form||event.target.name!=='children')return;
  const ids=new FormData(form).getAll('children').filter(id=>childById(id));
  $('#invitation-participants').textContent=names(ids)||'Choose at least one child';
});
document.addEventListener('keydown',event=>{if(event.target.matches('[role="tab"]')&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const options=['incoming','outgoing','history'];const current=options.indexOf(inviteTab);inviteTab=event.key==='Home'?'incoming':event.key==='End'?'history':options[(current+(event.key==='ArrowRight'?1:2))%3];render();$(`#tab-${inviteTab}`).focus();}});

// Fictional network fixtures. A production API must filter membership and opt-in
// server-side and must never send unlisted records or other families' codes.
const NETWORK_FAMILIES = [
  {id:'river',name:'River',guardians:['Taylor','Riley'],color:'lavender',listed:true,code:'RIVER-4M8P'},
  {id:'cedar',name:'Cedar',guardians:['Sam','Quinn'],color:'green',listed:true,code:'CEDAR-8N3K'},
  {id:'ash',name:'Ash',guardians:['Avery'],color:'peach',listed:true,code:'ASH-6T2W'},
  {id:'willow',name:'Willow',guardians:['Emma','Noah'],color:'yellow',listed:true,code:'WILLOW-3R7J'},
  {id:'birch',name:'Birch',guardians:['Sophie','Lee'],color:'blue',listed:true,code:'BIRCH-5C9H'},
  {id:'elm',name:'Elm',guardians:['Nora','Daniel'],color:'lavender',listed:true,code:'ELM-2F6B'},
  {id:'pine',name:'Pine',guardians:['Hazel'],color:'green',listed:false,code:'PINE-7K2M'},
];
let directoryQuery='';
let inviteDraft=null;
const sameFamily=(a,b)=>a.trim().toLocaleLowerCase()===b.trim().toLocaleLowerCase();
const normalizeInviteCode=value=>value.trim().toUpperCase().replace(/\s/g,'');
function listedFamilies(query='') {
  const list=NETWORK_FAMILIES.filter(f=>f.listed&&!sameFamily(f.name,state.family)).map(f=>({id:f.id,name:f.name,guardians:[...f.guardians],color:f.color,own:false}));
  if(state.directoryListed)list.push({id:'own-family',name:state.family,guardians:[state.parent],color:'blue',own:true});
  const term=query.trim().toLocaleLowerCase();
  return list.filter(f=>`${f.name} ${f.guardians.join(' ')}`.toLocaleLowerCase().includes(term)).sort((a,b)=>a.name.localeCompare(b.name));
}
function directoryCardStatus(entry) {
  if(entry.own)return {label:'Your family',tone:'blue',action:'settings',button:'Manage listing'};
  const family=state.families.find(f=>sameFamily(f.name,entry.name));
  const incoming=state.invites.find(i=>i.direction==='incoming'&&i.status==='pending'&&sameFamily(i.family,entry.name));
  if(incoming)return {label:'Invitation received',tone:'amber',action:'directory-received',button:'Review invitation',id:incoming.id};
  if(family?.connections.some(c=>c.status==='approved'))return {label:'Connected',tone:'green',action:'family-detail',button:'Manage connection',id:`f-${family.id}`};
  const outgoing=state.invites.find(i=>i.direction==='outgoing'&&i.status==='pending'&&sameFamily(i.family,entry.name));
  if(outgoing)return {label:'Invitation sent',tone:'amber',action:'directory-sent',button:'View invitation'};
  if(family?.peers.length)return {label:'No active connections',tone:'neutral',action:'family-detail',button:'Manage connection',id:`f-${family.id}`};
  return {label:'Open to invitations',tone:'neutral',action:'directory-invite',button:'Request a connection',id:entry.id};
}
function directoryCard(entry) {
  const status=directoryCardStatus(entry);
  return `<article class="directory-card"><div class="directory-card-top">${avatar(entry.name,entry.color)}<span class="pill ${status.tone}">${status.label}</span></div><h2>The ${esc(entry.name)} family</h2><p class="directory-guardians">${icon('users')}<span>${esc(entry.guardians.join(' & '))}<small>Parents & guardians</small></span></p><button class="card-action" data-action="${status.action}" ${status.id?`data-id="${esc(status.id)}"`:''}>${status.button}${icon('arrow')}</button></article>`;
}
function directoryResults() {
  const entries=listedFamilies(directoryQuery);
  return entries.length?entries.map(directoryCard).join(''):`<div class="empty-state">${icon('search')}<h3>No listed families match${directoryQuery.trim()?` “${esc(directoryQuery.trim())}”`:''}.</h3><p>Try another family or guardian name. A parent can also share an invite code with you.</p><div class="empty-actions">${directoryQuery.trim()?actionButton('Clear search','clear-directory-search'):''}${actionButton('Use an invite code','use-invite-code')}</div></div>`;
}
function directoryCount() {const count=listedFamilies(directoryQuery).length;return `${count} ${count===1?'family':'families'}${directoryQuery.trim()?' found':' listed'}`;}
function updateDirectoryResults() {$('#directory-results').innerHTML=directoryResults();$('#directory-count').textContent=directoryCount();}
function directoryPage() {
  return `<section class="directory-welcome"><span class="directory-welcome-icon">${icon('users')}</span><div><h2>A familiar name is a good place to start.</h2><p>Only families who choose to be listed appear here. Find someone you know, then send a request for your children to connect.</p></div></section><section class="directory-visibility-summary"><div>${icon(state.directoryListed?'users':'lock')}<p><strong>Your family is ${state.directoryListed?'listed':'unlisted'}.</strong> ${state.directoryListed?'Other parents can find your family and guardian name.':'Other parents can find you when you share your invite code.'}</p></div><div class="inline-actions"><button class="text-button blue-text" data-action="settings">Manage visibility</button><button class="text-button blue-text" data-action="share-invite-code">Share your code ${icon('arrow')}</button></div></section><div class="directory-toolbar"><label class="directory-search" for="directory-search">${icon('search')}<span class="sr-only">Search listed families or guardians</span><input id="directory-search" type="search" maxlength="80" value="${esc(directoryQuery)}" placeholder="Search family or guardian name" autocomplete="off" aria-controls="directory-results"></label><span id="directory-count" class="directory-count" role="status" aria-live="polite">${directoryCount()}</span></div><div id="directory-results" class="directory-grid">${directoryResults()}</div><div class="section-footnote">${icon('shield')} Listings show family and guardian names only. Calling still needs approval for each child.</div>`;
}
function directorySettings() {
  return `<section class="panel settings-panel directory-settings"><div class="section-heading"><h2>Directory visibility</h2><span class="pill ${state.directoryListed?'green':'neutral'}">${state.directoryListed?'Listed':'Unlisted'}</span></div><div class="visibility-control"><div><h3 id="directory-toggle-label">Let parents in this network find our family</h3><p id="directory-toggle-description">Share your family name and guardian name in the directory. Your children’s details stay private.</p></div><button class="switch" role="switch" aria-checked="${state.directoryListed}" aria-labelledby="directory-toggle-label" aria-describedby="directory-toggle-description" data-action="directory-visibility"><span></span></button></div><div class="listing-preview"><span class="mini-label">${state.directoryListed?'YOUR CURRENT LISTING':'YOUR LISTING PREVIEW'}</span><div class="person-line">${avatar(state.family,'blue','small-avatar')}<div><h3>The ${esc(state.family)} family</h3><span>${esc(state.parent)} · Parent & guardian</span></div></div></div><p class="form-note">Hiding your listing leaves existing connections and invitations unchanged.</p><div class="inline-actions"><button class="text-button blue-text" data-action="directory">Explore the directory ${icon('arrow')}</button><button class="text-button blue-text" data-action="share-invite-code">Share your invite code ${icon('copy')}</button></div></section>`;
}
function resolveInviteDraft() {
  if(!inviteDraft)return null;
  const target=NETWORK_FAMILIES.find(f=>f.id===inviteDraft.id&&!sameFamily(f.name,state.family));
  if(!target)return null;
  if(inviteDraft.source==='directory'&&target.listed)return target;
  if(inviteDraft.source==='code'&&normalizeInviteCode(target.code)===inviteDraft.code)return target;
  return null;
}
function inviteCodeDialog() {
  openDialog('Have a family’s invite code?',`<p class="dialog-intro">Enter the code a parent shared with you. This also works for families who keep their listing private.</p>${textField('Family invite code','code','','required maxlength="40" autocomplete="off" spellcheck="false" placeholder="e.g. WILLOW-3R7J"')}<p class="form-note">A code identifies the family. You’ll choose your children and send an invitation next.</p><div class="demo-notice">For this draft, try <strong>WILLOW-3R7J</strong> or the unlisted-family example <strong>PINE-7K2M</strong>.</div>`,{form:'invite-code',submit:'Find family'});
}
function shareInviteCode() {
  openDialog('A little code. A new connection.',`<p class="dialog-intro">Share this code directly with a parent you know. They can send your family an invitation even when you’re unlisted.</p><label class="field"><span>Your family’s invite code</span><div class="input-with-action"><input id="share-family-code" value="${esc(state.inviteCode)}" readonly spellcheck="false"><button type="button" data-action="copy-invite-code">Copy ${icon('copy')}</button></div></label><div class="listing-preview"><span class="mini-label">WHAT THEY’LL SEE</span><div class="person-line">${avatar(state.family,'blue','small-avatar')}<div><h3>The ${esc(state.family)} family</h3><span>${esc(state.parent)} · Parent & guardian</span></div></div></div><p class="form-note">Sharing a code does not approve calling. You still review each invitation.</p><div class="demo-notice">This code is a prototype example. Families on other devices cannot use it to reach your browser-tab data.</div>`);
}
async function copyInviteCode() {
  const input=$('#share-family-code');
  try {if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(state.inviteCode);toast('Family invite code copied.');return;}}catch{}
  input.focus();input.select();
  try {if(document.execCommand?.('copy')){toast('Family invite code copied.');return;}}catch{}
  toast('Code selected. Copy it to share with a parent you know.');
}


const normalizeGuardianEmail=value=>String(value||'').trim().toLocaleLowerCase();
const validGuardianEmail=email=>/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
function guardianEmailTaken(email) {return normalizeGuardianEmail(state.email)===normalizeGuardianEmail(email)||state.guardians.some(g=>normalizeGuardianEmail(g.email)===normalizeGuardianEmail(email));}
function guardianNameTaken(name) {return [state.parent,...state.guardians.map(g=>g.name)].some(n=>n.trim().toLocaleLowerCase()===name.trim().toLocaleLowerCase());}
function guardianInviteStatus(invitation,now=Date.now()) {
  if(invitation.status!=='pending')return invitation.status;
  return Number.isFinite(invitation.expiresAt)&&invitation.expiresAt>now?'pending':'expired';
}
function newGuardianInvitation(name,email) {const now=Date.now();return {id:uid(),name,email,status:'pending',createdAt:now,expiresAt:now+7*24*60*60*1000};}
function guardianInviteDate(timestamp) {return new Date(timestamp).toLocaleDateString('en-US',{month:'short',day:'numeric'});}
function guardiansPanel() {
  const activeInvites=state.guardianInvites.filter(i=>['pending','expired'].includes(guardianInviteStatus(i)));
  const pastInvites=state.guardianInvites.filter(i=>!['pending','expired'].includes(guardianInviteStatus(i)));
  return `<section class="panel settings-panel guardian-panel"><div class="section-heading"><h2>Parents & guardians</h2><button type="button" class="button secondary small" data-action="invite-guardian">${icon('plus')} Invite a guardian</button></div><div class="guardian-row"><div class="person-line">${avatar(state.parent,'yellow','small-avatar')}<div><h3>${esc(state.parent)}</h3><span>${esc(state.email)}</span></div></div><span class="pill blue">You · Primary</span></div>${state.guardians.map(g=>`<div class="guardian-row"><div class="person-line">${avatar(g.name,'blue','small-avatar')}<div><h3>${esc(g.name)}</h3><span>${esc(g.email)}</span></div></div><div class="guardian-row-actions"><span class="pill green">Guardian</span><button type="button" class="text-button danger-text" data-action="remove-guardian" data-id="${g.id}" aria-label="Remove ${esc(g.name)} as a guardian">Remove</button></div></div>`).join('')}${!state.guardians.length&&!activeInvites.length?'<p class="guardian-empty">Invite another parent or guardian to help look after your family’s phones and connections.</p>':''}${activeInvites.length?`<div class="guardian-invitations"><h3>Guardian invitations</h3>${activeInvites.map(i=>{const pending=guardianInviteStatus(i)==='pending';return `<article class="guardian-invitation"><div class="guardian-invitation-heading"><div><h4>${esc(i.name)}</h4><p>${esc(i.email)}</p></div><span class="pill ${pending?'amber':'neutral'}">${pending?'Pending':'Expired'}</span></div><p class="guardian-invite-timing">${pending?'Expires':'Expired'} ${guardianInviteDate(i.expiresAt)} · ${pending?'No family access until they accept.':'This invitation can no longer be used.'}</p><div class="guardian-invite-actions">${pending?`<button type="button" class="text-button blue-text" data-action="preview-guardian-invite" data-id="${i.id}">Preview invitation ${icon('arrow')}</button>`:''}<button type="button" class="text-button" data-action="resend-guardian-invite" data-id="${i.id}">${pending?'Resend':'Send a new invitation'}</button>${pending?`<button type="button" class="text-button danger-text" data-action="cancel-guardian-invite" data-id="${i.id}">Cancel</button>`:''}</div></article>`;}).join('')}</div>`:''}${pastInvites.length?`<details class="guardian-history"><summary>Past invitations (${pastInvites.length})</summary>${pastInvites.map(i=>`<div class="guardian-history-row"><span>${esc(i.name)}<small>${esc(i.email)}</small></span><span class="pill neutral">${esc(i.status==='replaced'?'Replaced':i.status[0].toUpperCase()+i.status.slice(1))}</span></div>`).join('')}</details>`:''}<div class="info-strip">${icon('shield')}<p>Guardians can manage children, phones, contacts, and calling permissions. The primary guardian manages who has guardian access.</p></div></section>`;
}
function guardianAccessSummary() {
  return `<div class="guardian-access"><h3>Guardian access includes</h3><ul><li>${icon('check')} Manage children, phones, and dial shortcuts</li><li>${icon('check')} Approve connections and external contacts</li><li>${icon('check')} Update quiet hours and family settings</li></ul></div>`;
}
function inviteGuardianDialog() {
  openDialog('A little help on the front porch.',`<p class="dialog-intro">Invite another parent or guardian to join the ${esc(state.family)} family. They’ll use their own account to help manage the same family.</p>${textField('Guardian’s name','name','','required maxlength="80" autocomplete="off" placeholder="e.g. Drew"')}${textField('Email address','email','','type="email" required maxlength="254" autocomplete="off" placeholder="drew@example.com"')}${guardianAccessSummary()}<p class="form-note">Their invitation lasts 7 days. Access starts only after they accept, and you can cancel the invitation at any time.</p><div class="demo-notice">Design preview: use fictional details. No email will be sent.</div>`,{form:'invite-guardian',submit:'Send invitation'});
}
function guardianInvitationCreated(id) {
  const invitation=state.guardianInvites.find(i=>i.id===id);if(!invitation)return;
  openDialog('Their invitation is ready.',`<div class="person-line invitation-family">${avatar(invitation.name,'blue')}<div><h3>${esc(invitation.name)}</h3><span>${esc(invitation.email)}</span></div></div><p class="dialog-intro">${esc(invitation.name)} can join the ${esc(state.family)} family by accepting this invitation. It expires ${guardianInviteDate(invitation.expiresAt)}.</p><div class="demo-notice">No email was sent. Preview the recipient’s invitation below to try joining this demo family.</div><div class="guardian-complete-actions">${actionButton('Back to family settings','settings')}${actionButton('Preview invitation','preview-guardian-invite',id,'','arrow')}</div>`);
}
function guardianJoinDialog(id,mode='create') {
  const invitation=state.guardianInvites.find(i=>i.id===id);
  if(!invitation||guardianInviteStatus(invitation)!=='pending'){
    openDialog('This invitation is no longer available.',`<p class="dialog-intro">It may have expired, been cancelled, or already been used. Ask the primary guardian for a new invitation.</p>${actionButton('Back to family settings','settings')}`);return;
  }
  const login=mode==='login';
  openDialog(`Join the ${esc(state.family)} family.`,`<div class="demo-notice">Recipient preview. Completing this form adds a guardian to the demo family; no account is created. You’ll return to the primary guardian’s view.</div><p class="dialog-intro">${esc(state.parent)} invited you to help manage the ${esc(state.family)} family.</p><div class="guardian-account-modes" role="group" aria-label="Choose account option"><button type="button" aria-pressed="${!login}" class="${!login?'selected':''}" data-action="guardian-join-mode" data-id="${id}" data-mode="create">Create an account</button><button type="button" aria-pressed="${login}" class="${login?'selected':''}" data-action="guardian-join-mode" data-id="${id}" data-mode="login">I already have an account</button></div>${textField('Your name','name',invitation.name,'required maxlength="80" autocomplete="off"')}${textField('Invited email address','email',invitation.email,'type="email" required readonly autocomplete="off"')}<p class="form-note">${login?'Log in with':'Your invitation is for'} this email address to join the family.</p>${textField(login?'Password':'Choose a password','password','','type="password" required autocomplete="off" placeholder="Any demo password"')}${guardianAccessSummary()}<p class="form-note">You’ll join this existing family and share its children, phones, contacts, and connections. The primary guardian can remove your access later.</p>`,{form:'join-as-guardian',submit:login?'Log in & join family':'Create account & join family',extra:`data-id="${id}"`,eyebrow:'GUARDIAN INVITATION'});
}
function resendGuardianInvite(id) {
  const previous=state.guardianInvites.find(i=>i.id===id);
  if(!previous||!['pending','expired'].includes(guardianInviteStatus(previous)))return;
  if(guardianEmailTaken(previous.email)){toast('This person is already a guardian in your family.');return;}
  if(state.guardianInvites.some(i=>i.id!==id&&normalizeGuardianEmail(i.email)===normalizeGuardianEmail(previous.email)&&guardianInviteStatus(i)==='pending')){toast('A newer invitation is already waiting for this email.');return;}
  previous.status='replaced';
  const next=newGuardianInvitation(previous.name,previous.email);state.guardianInvites.unshift(next);
  finish(`A new guardian invitation for ${next.name} is ready. The previous invitation can no longer be used.`);
  guardianInvitationCreated(next.id);
}

window.addEventListener('hashchange',route);
route();

// Optional agent navigation uses the same client-side routes as the visible UI.
if(document.modelContext?.registerTool){
  const lifecycle=new AbortController();
  const tools=[{name:'frontporch_read_demo',description:'Read fictional family setup and counts in this local UI prototype. Does not read a backend.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute(){return {family:state.family,children:state.children.map(c=>({id:c.id,name:c.name,extension:c.extension,status:c.phoneStatus})),connections:state.families.length,pendingInvitations:pendingCount(),contacts:state.contacts.length};}},{name:'frontporch_navigate_demo',description:'Open a prototype section. Only changes the visible view; does not approve calls or send invitations.',inputSchema:{type:'object',properties:{section:{type:'string',enum:['overview','children','circle','directory','invites','contacts','settings']}},required:['section'],additionalProperties:false},annotations:{readOnlyHint:false},execute(input){if(!input||!['overview','children','circle','directory','invites','contacts','settings'].includes(input.section))throw new Error('Unknown prototype section');history.replaceState(null,'',`#family/${input.section}`);route();return {section,visible:true};}}];
  for(const tool of tools){try{Promise.resolve(document.modelContext.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{}}
  window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
}
