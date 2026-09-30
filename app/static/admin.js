const buttons=[...document.querySelectorAll('.status-choice')], status=document.getElementById('status');
function select(v){status.value=v;buttons.forEach(b=>b.classList.toggle('selected',b.dataset.status===v));}
buttons.forEach(b=>b.onclick=()=>select(b.dataset.status));

async function load(){
	const r=await fetch('/api/state');
	const s=await r.json();
	select(s.status);
	messageInput.value=s.message||'';
	returnInput.value=s.return_time||'';
}

statusForm.onsubmit=async e=>{
	e.preventDefault();
	closeKeyboard();
	const data=Object.fromEntries(new FormData(statusForm));
	const r=await fetch('/api/state',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
	if(r.ok)location.href='/';else alert('Could not update sign.');
};

updateButton.onclick=async()=>{
	if(!confirm('Update the Office Door Sign now? The display will restart briefly.'))return;
	updateButton.disabled=true;
	updateButton.querySelector('.button-label').textContent='Updating…';
	try{
		const r=await fetch('/api/update',{method:'POST'});
		if(!r.ok){const data=await r.json().catch(()=>({}));throw new Error(data.error||'Could not start update.');}
		alert('Update started. The sign will restart when the update is complete.');
		location.href='/';
	}catch(err){
		alert(err.message);
		updateButton.disabled=false;
		updateButton.querySelector('.button-label').textContent='Update';
	}
};

const keyboard=document.getElementById('onscreenKeyboard');
const keyboardKeys=document.getElementById('keyboardKeys');
const keyboardFieldLabel=document.getElementById('keyboardFieldLabel');
const keyboardInputs=[messageInput,returnInput];
let activeInput=null;
let shifted=false;

const keyRows=[
	['1','2','3','4','5','6','7','8','9','0'],
	['q','w','e','r','t','y','u','i','o','p'],
	['a','s','d','f','g','h','j','k','l'],
	['shift','z','x','c','v','b','n','m','backspace'],
	['clear',',','space','.','-','\'','?']
];

function renderKeyboard(){
	keyboardKeys.replaceChildren();
	keyRows.forEach(row=>{
		const rowEl=document.createElement('div');
		rowEl.className='keyboard-row';
		row.forEach(key=>{
			const button=document.createElement('button');
			button.type='button';
			button.className='keyboard-key';
			button.dataset.key=key;
			if(['shift','backspace','clear','space'].includes(key))button.classList.add(`key-${key}`);
			if(key==='shift')button.classList.toggle('active',shifted);
			const labels={shift:'⇧ Shift',backspace:'⌫',clear:'Clear',space:'Space'};
			button.textContent=labels[key]||(shifted&&/^[a-z]$/.test(key)?key.toUpperCase():key);
			rowEl.appendChild(button);
		});
		keyboardKeys.appendChild(rowEl);
	});
}

function openKeyboard(input){
	activeInput=input;
	keyboardFieldLabel.textContent=input===messageInput?'Message':'Return time';
	keyboard.classList.add('open');
	keyboard.setAttribute('aria-hidden','false');
	document.body.classList.add('keyboard-open');
	renderKeyboard();
	setTimeout(()=>input.scrollIntoView({behavior:'smooth',block:'center'}),50);
}

function closeKeyboard(){
	keyboard.classList.remove('open');
	keyboard.setAttribute('aria-hidden','true');
	document.body.classList.remove('keyboard-open');
	activeInput=null;
}

function insertText(text){
	if(!activeInput)return;
	const start=activeInput.selectionStart??activeInput.value.length;
	const end=activeInput.selectionEnd??start;
	const next=activeInput.value.slice(0,start)+text+activeInput.value.slice(end);
	if(next.length>activeInput.maxLength)return;
	activeInput.value=next;
	const pos=start+text.length;
	activeInput.setSelectionRange(pos,pos);
	activeInput.focus({preventScroll:true});
}

keyboardInputs.forEach(input=>{
	input.setAttribute('inputmode','none');
	input.addEventListener('focus',()=>openKeyboard(input));
	input.addEventListener('click',()=>openKeyboard(input));
});

keyboard.addEventListener('pointerdown',e=>e.preventDefault());
keyboard.addEventListener('click',e=>{
	const button=e.target.closest('button[data-key]');
	if(!button)return;
	const key=button.dataset.key;
	if(key==='done'){closeKeyboard();return;}
	if(key==='shift'){shifted=!shifted;renderKeyboard();return;}
	if(key==='backspace'){
		if(!activeInput)return;
		const start=activeInput.selectionStart??activeInput.value.length;
		const end=activeInput.selectionEnd??start;
		if(start!==end){activeInput.value=activeInput.value.slice(0,start)+activeInput.value.slice(end);activeInput.setSelectionRange(start,start);}
		else if(start>0){activeInput.value=activeInput.value.slice(0,start-1)+activeInput.value.slice(end);activeInput.setSelectionRange(start-1,start-1);}
		activeInput.focus({preventScroll:true});
		return;
	}
	if(key==='clear'){activeInput.value='';activeInput.focus({preventScroll:true});return;}
	insertText(key==='space'?' ':(shifted&&/^[a-z]$/.test(key)?key.toUpperCase():key));
	if(shifted&&/^[a-z]$/.test(key)){shifted=false;renderKeyboard();}
});

renderKeyboard();
load();
