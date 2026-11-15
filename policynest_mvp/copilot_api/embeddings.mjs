// Shared local CPU embedding model for indexing and query vectors. No applicant data is sent to a service.
import {pipeline,env} from '@huggingface/transformers';
import fs from 'node:fs';
import readline from 'node:readline';
import {fileURLToPath} from 'node:url';
env.cacheDir=fileURLToPath(new URL('../../.model-cache/',import.meta.url));
const model=await pipeline('feature-extraction','Xenova/all-MiniLM-L6-v2',{dtype:'q8'});
async function vector(text){const out=await model(text,{pooling:'mean',normalize:true});return Array.from(out.data)}
if(process.argv[2]==='index'){
  const input=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
  for(const c of input.chunks)c.vector=await vector(c.head+' '+c.text);
  input.embedding_model='Xenova/all-MiniLM-L6-v2';input.dimensions=384;
  fs.writeFileSync(process.argv[4],JSON.stringify(input));console.log(`Indexed ${input.chunks.length} chunks`);
}else{
  console.log(JSON.stringify({ready:true}));
  for await(const line of readline.createInterface({input:process.stdin,crlfDelay:Infinity})){
    try{const q=JSON.parse(line);console.log(JSON.stringify({vector:await vector(q.text)}))}catch{console.log(JSON.stringify({error:'embedding_failed'}))}
  }
}
