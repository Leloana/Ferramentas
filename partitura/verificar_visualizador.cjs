const puppeteer = require('puppeteer');
const assert = require('node:assert/strict');
const fs = require('node:fs');

(async () => {
  const executablePath = ['C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(fs.existsSync);
  const browser = await puppeteer.launch({ executablePath, headless:true,
    args:['--autoplay-policy=no-user-gesture-required'], defaultViewport:{width:1440,height:1000} });
  try {
    const page = await browser.newPage();
    const erros=[];
    page.on('pageerror', e => erros.push(e.message));
    await page.setRequestInterception(true);
    page.on('request', r => /^(http:\/\/127\.0\.0\.1:8030|data:)/.test(r.url()) ? r.continue() : r.abort());
    await page.goto('http://127.0.0.1:8030/#biblioteca',{waitUntil:'domcontentloaded'});
    await page.waitForFunction(() => musicas.length>0);
    await page.evaluate(() => {
      escolha.nivel='medio'; escolha.versao='HibridoAMT'; selecionar('No Surprises (Radiohead)');
    });
    await page.waitForSelector('#partituraInterativa svg',{timeout:60000});
    await page.waitForFunction(() => document.querySelector('#audioPartitura').readyState>=1);
    const tempo = await page.evaluate(() => leitorPartitura.quadros.filter(q=>q.notas.length)[20].tempo+.02);
    await page.evaluate(t => { document.querySelector('#audioPartitura').currentTime=t; },tempo);
    await page.waitForFunction(() => {
      const t=document.querySelector('#audioPartitura').currentTime;
      const esperado=leitorPartitura.quadros.filter(q=>q.tempo<=t).at(-1)?.notas || [];
      const real=[...document.querySelectorAll('.nota-tocando')].map(n=>n.id);
      return esperado.length>0 && esperado.length===real.length && esperado.every(id=>real.includes(id));
    });
    const destaque = await page.evaluate(() => {
      const t=document.querySelector('#audioPartitura').currentTime;
      const esperado=leitorPartitura.quadros.filter(q=>q.tempo<=t).at(-1).notas.sort();
      return {esperado,real:[...document.querySelectorAll('.nota-tocando')].map(n=>n.id).sort()};
    });
    assert.deepEqual(destaque.real,destaque.esperado);
    // A barra deve atravessar uma pausa real sem depender de notas ativas.
    const pausa = await page.evaluate(() => {
      for (let i=0;i<leitorPartitura.quadros.length-1;i++) {
        const a=leitorPartitura.quadros[i],b=leitorPartitura.quadros[i+1];
        if (a.notas.length || b.tempo-a.tempo<.4) continue;
        const m=leitorPartitura.percurso.find(m=>m.inicio<=a.tempo+.01 && m.fim>=b.tempo-.01);
        if (m) return [a.tempo+(b.tempo-a.tempo)*.2,a.tempo+(b.tempo-a.tempo)*.8];
      }
      return null;
    });
    assert.ok(pausa,'Falta uma pausa para a regressão');
    const posicoes=[];
    for(const t of pausa) {
      await page.evaluate(t=>{document.querySelector('#audioPartitura').currentTime=t;leitorPartitura.buscar();},t);
      posicoes.push(await page.evaluate(()=>{
        const c=[...document.querySelectorAll('.cursor-partitura')].filter(c=>!c.hidden);
        return {barras:c.length,x:c[0]?.style.left,notas:document.querySelectorAll('.nota-tocando').length};
      }));
    }
    assert.ok(posicoes.every(p=>p.barras===1 && p.notas===0),JSON.stringify(posicoes));
    assert.ok(parseFloat(posicoes[1].x)>parseFloat(posicoes[0].x)+2,JSON.stringify(posicoes));
    await page.evaluate(t=>{document.querySelector('#audioPartitura').currentTime=t;leitorPartitura.buscar();},pausa[0]);
    await page.evaluate(()=>document.querySelector('#audioPartitura').play());
    const espera=pausa[0]+Math.min(.15,(pausa[1]-pausa[0])/2);
    await page.waitForFunction(t=>document.querySelector('#audioPartitura').currentTime>t,{},espera);
    const durantePausa=await page.evaluate(()=>{
      document.querySelector('#audioPartitura').pause();
      const c=[...document.querySelectorAll('.cursor-partitura')].find(c=>!c.hidden);
      return {x:parseFloat(c.style.left),notas:document.querySelectorAll('.nota-tocando').length};
    });
    assert.equal(durantePausa.notas,0);
    assert.ok(durantePausa.x>parseFloat(posicoes[0].x)+1);
    // E também deve andar entre dois instantes do mesmo acorde sustentado.
    await page.evaluate(t=>{document.querySelector('#audioPartitura').currentTime=t;},tempo);
    await page.evaluate(() => document.querySelector('#audioPartitura').play());
    await page.waitForFunction(t => document.querySelector('#audioPartitura').currentTime>t+.15,{},tempo);
    await page.evaluate(() => document.querySelector('#audioPartitura').pause());
    const salto = await page.evaluate(() => {
      const [id,t]=Object.entries(leitorPartitura.inicios).find(([,t])=>t>20);
      leitorPartitura.elementos.get(id).dispatchEvent(new MouseEvent('click',{bubbles:true}));
      return t;
    });
    await page.waitForFunction(t => Math.abs(document.querySelector('#audioPartitura').currentTime-t)<.01,{},salto);
    await page.select('#zoomPartitura','150');
    assert.equal(await page.$eval('.folha-partitura',el=>el.style.width),'150%');
    await page.screenshot({path:'trabalho/visualizador.png'});
    await page.setViewport({width:390,height:844});
    const largura = await page.evaluate(() => ({tela:innerWidth,documento:document.documentElement.scrollWidth}));
    assert.ok(largura.documento<=largura.tela+1,JSON.stringify(largura));
    await page.screenshot({path:'trabalho/visualizador-mobile.png'});
    await page.evaluate(() => document.querySelector('#audioOriginal').play());
    await page.waitForFunction(() => document.querySelector('#audioPartitura').paused && !document.querySelector('.nota-tocando'));
    await page.evaluate(() => document.querySelector('#audioOriginal').pause());
    await page.click('[data-nivel="dificil"]');
    await page.waitForSelector('#partituraInterativa svg',{timeout:60000});
    assert.equal(await page.$eval('[data-versao="HibridoAMT"]',el=>el.classList.contains('ativa')),true);
    assert.deepEqual(erros,[]);
    console.log('OK: barra avança durante pausa real, destaque, reprodução, busca, clique, zoom e troca de player; desktop e celular.');
  } finally {
    await browser.close();
  }
})().catch(e=>{console.error(e);process.exitCode=1;});
