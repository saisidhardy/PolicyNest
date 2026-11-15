// Usage: node tools/ingest_posp_manual.mjs <manual.pdf> <output.json>
// Preserve page and visual row boundaries; never execute source text.
import fs from 'node:fs';
import crypto from 'node:crypto';
import {getDocument} from 'pdfjs-dist/legacy/build/pdf.mjs';
const [input, output] = process.argv.slice(2);
if (!input || !output) throw new Error('Expected input PDF and output JSON paths');
const bytes = fs.readFileSync(input);
const pdf = await getDocument({data:new Uint8Array(bytes),useSystemFonts:true}).promise;
if(pdf.numPages!==7) throw new Error('Expected the approved seven-page manual');
let section='Introduction', subsection='', chunks=[], pages=[];
for(let page=1;page<=pdf.numPages;page++){
  const pageStartSection=section,pageStartSubsection=subsection;
  const p=await pdf.getPage(page), content=await p.getTextContent();
  const rows=[];
  for(const item of content.items){
    if(!item.str?.trim()) continue;
    const y=item.transform[5];
    let row=rows.find(r=>Math.abs(r.y-y)<2);
    if(!row){row={y,items:[]};rows.push(row)}
    row.items.push({x:item.transform[4],text:item.str});
  }
  // PDF content order keeps wrapped table cells together; geometric row flattening interleaves columns.
  const items=content.items.filter(i=>i.str?.trim());
  const lines=[];let current='',previous=null;
  for(const item of items){
    if(previous&&(Math.abs(previous.transform[5]-item.transform[5])>2||item.transform[4]<previous.transform[4]-3)){if(current)lines.push(current);current=''}
    current+=(current?' ':'')+item.str;previous=item;
  }
  if(current)lines.push(current);
  pages.push({page_number:page,lines});
  let buf=[];
  function flush(){if(!buf.length)return;const text=buf.join('\n');chunks.push({document_id:'posp-operational-manual',document_name:'POSP RAG System Knowledge Base & Policy Manual',page_number:page,section,subsection,content_type:/Q\d:/.test(text)?'Q&A':/3\.2/.test(subsection)?'troubleshooting':/2\.1/.test(subsection)?'workflow':/5\./.test(subsection)?'compliance':'policy',version:crypto.createHash('sha256').update(bytes).digest('hex'),source_type:'operational_reference',source_classification:'Unverified or potentially outdated claim',text});buf=[]}
  for(const line of lines){
    if(/Page \d of 7/.test(line))continue;
    if(/^\d+\.\d+\s/.test(line)){flush();subsection=line}
    else if(/^\d+\.\s+[A-Z]/.test(line)){flush();section=line;subsection=''}
    else if(/^Q\d+:/.test(line))flush();
    buf.push(line);
  }
  flush();
  const header=items.findIndex(i=>/^(Line of Business|Document Type|System Symptom \/)/.test(i.str));
  if(header>=0){
    let tableSection=pageStartSection,tableSubsection=pageStartSubsection;
    for(const item of items.slice(0,header)){
      if(/^\d+\.\d+\s/.test(item.str))tableSubsection=item.str;
      else if(/^\d+\.\s+[A-Z]/.test(item.str)){tableSection=item.str;tableSubsection=''}
    }
    const first=items[header],second=items.slice(header).find(i=>/^(Permitted POS Products|Acceptance Criteria|Root Cause)$/.test(i.str)),third=items.slice(header).find(i=>/^(Key Regulatory Caps|Common Rejection Triggers|Standard Resolution Steps)/.test(i.str));
    if(second&&third){
      let cells=['','',''],lastCol=0,tableRows=[];
      for(const item of items.slice(header)){
        if(item.transform[5]<60||(/^\d+\./.test(item.str)&&item.transform[4]<first.transform[4]-3))break;
        const col=item.transform[4]>=third.transform[4]-3?2:item.transform[4]>=second.transform[4]-3?1:0;
        if(col===0&&lastCol===2){tableRows.push(cells);cells=['','','']}
        cells[col]+=(cells[col]?' ':'')+item.str;lastCol=col;
      }
      if(cells.some(Boolean))tableRows.push(cells);
      const labels=tableRows.shift();
      for(const row of tableRows){
        const text=row.map((cell,i)=>labels[i]+': '+cell).join('\n');
        chunks.push({document_id:'posp-operational-manual',document_name:'POSP RAG System Knowledge Base & Policy Manual',page_number:page,section:tableSection,subsection:tableSubsection+' / '+row[0],content_type:/Root Cause/.test(labels[1])?'troubleshooting':'policy',version:crypto.createHash('sha256').update(bytes).digest('hex'),source_type:'operational_reference',source_classification:'Unverified or potentially outdated claim',text});
      }
    }
  }
}
fs.writeFileSync(output,JSON.stringify({document_id:'posp-operational-manual',page_count:pdf.numPages,pages,chunks},null,2));
console.log(`Extracted ${pdf.numPages} pages and ${chunks.length} page-aware semantic sections`);
