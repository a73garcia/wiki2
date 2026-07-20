function editorFor(button){
  const bar=button.closest('.toolbar');
  return bar ? document.getElementById(bar.dataset.target) : null;
}
function insertText(t,open,close='',mode='wrap'){
  const a=t.selectionStart,z=t.selectionEnd,sel=t.value.slice(a,z);
  let value='';
  if(mode==='insert') value=open;
  else if(mode==='code') value=`\n\n\`\`\`${open}\n${sel}\n\`\`\`\n\n`;
  else value=open+sel+close;
  t.setRangeText(value,a,z,'end'); t.focus(); t.dispatchEvent(new Event('input',{bubbles:true}));
}
function indent(t,remove=false){
  const value=t.value,a=t.selectionStart,z=t.selectionEnd;
  const start=value.lastIndexOf('\n',Math.max(0,a-1))+1;
  let end=value.indexOf('\n',z); if(end<0)end=value.length;
  const lines=value.slice(start,end).split('\n');
  const changed=lines.map(line=>remove?line.replace(/^(\t| {1,4})/,''):'    '+line).join('\n');
  t.setRangeText(changed,start,end,'select'); t.focus(); t.dispatchEvent(new Event('input',{bubbles:true}));
}
document.addEventListener('click',async e=>{
  const b=e.target.closest('.toolbar button'); if(!b)return;
  const t=editorFor(b); if(!t)return;
  if(b.dataset.insert!==undefined) insertText(t,b.dataset.insert,'','insert');
  else if(b.dataset.wrap!==undefined) insertText(t,b.dataset.wrap,b.dataset.wrap);
  else if(b.dataset.wrapOpen!==undefined) insertText(t,b.dataset.wrapOpen,b.dataset.wrapClose||'');
  else if(b.dataset.code!==undefined) insertText(t,b.dataset.code,'','code');
  else if(b.dataset.indent) indent(t,false);
  else if(b.dataset.outdent) indent(t,true);
  else if(b.dataset.image){
    const input=document.querySelector(`.bau-image-input[data-editor="${t.id}"]`);
    if(input){input.value='';input.click();}
  }
});
document.addEventListener('keydown',e=>{
  if(e.key!=='Tab'||e.target.tagName!=='TEXTAREA')return;
  e.preventDefault(); indent(e.target,e.shiftKey);
});
document.addEventListener('change',async e=>{
  const input=e.target.closest('.bau-image-input'); if(!input||!input.files?.[0])return;
  const t=document.getElementById(input.dataset.editor); if(!t)return;
  const status=document.querySelector(`[data-status="${t.id}"]`);
  if(status)status.textContent='Subiendo imagen…';
  const form=new FormData(); form.append('image',input.files[0]);
  try{
    const response=await fetch('/upload-image',{method:'POST',body:form});
    const result=await response.json();
    if(!response.ok||!result.ok)throw new Error(result.error||'No se pudo subir la imagen.');
    const name=input.files[0].name.replace(/\.[^.]+$/,'').replace(/[-_]+/g,' ');
    const pos=t.selectionStart; t.setRangeText(`\n\n[[imagen:${result.filename}|${name}]]\n\n`,pos,pos,'end'); t.focus();
    if(status)status.textContent='Imagen insertada.';
  }catch(err){if(status)status.textContent=err.message;}
});
