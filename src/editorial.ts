const local:Record<string,RegExp>={
 KR:/한국|원화|원[·/\-]달러|달러[·/\-]원|한국은행|금감원|금융위|Korea|韩[国元]/i,
 VN:/Việt Nam|Việt|VND|đồng|Ngân hàng Nhà nước|越南/i,
 TH:/ไทย|บาท|ธปท|Thailand|baht|泰[国铢]/i,
 ID:/Indonesia|rupiah|OJK|Bappebti|Bank Indonesia|印尼/i,
 BR:/Brasil|brasileir|Selic|real|reais|巴西/i,
 AR:/مصر|مصري|العراق|عراقي|الكويت|كويتي|السعود|الإمارات|لبنان|قطر|البحرين|الأردن|سوري|المغرب|تونس|الجزائر|عمان|Middle East|Egypt|Iraq|Kuwait|Saudi|UAE|Dubai|埃及|伊拉克|科威特|中东/i,
 LA:/Colombia|colombian|México|mexican|Argentina|argentin|Chile|chilen|Perú|peruan|Uruguay|Ecuador|Bolivia|Venezuela|Latinoamérica|América Latina|哥伦比亚|墨西哥|阿根廷|智利|秘鲁/i,
 JP:/日本|日銀|円|金融庁|Japan|yen|BOJ/i,
 TW:/台北|臺北|高雄|台中|臺中|新北|台南|臺南|金管會|金管会|台灣|臺灣|台幣|新臺幣|新台幣|台湾|台币|Taiwan|TWD/i,
 SA:/India|Indian|Pakistan|rupee|RBI|SEBI|SBP|INR|PKR|印度|巴基斯坦|卢比|孟加拉|Bangladesh|Sri Lanka/i,
 AF:/Africa|Nigeria|naira|Kenya|shilling|Ghana|cedi|rand|非洲|南非|尼日利亚|肯尼亚/i,
 CN:/中国|中國|人民币|人民幣|中国人民银行|外汇局|外匯局|境内|境內|China|PBOC|yuan|renminbi|CNY/i
};
const finance=/外汇|外匯|汇率|匯率|货币|貨幣|利率|央行|美联储|黄金|黃金|交易商|出金|诈骗|詐騙|\b(forex|currency|monetary|central bank|interest rate|broker|withdrawal|fraud|scam|Fed|ECB|BOJ|gold)\b|환율|원화|금리|통화|한국은행|경상수지|투자.*사기|tỷ giá|ngoại hối|tiền tệ|lãi suất|Ngân hàng Nhà nước|lừa đảo|giá vàng|ค่าเงิน|เงินบาท|อัตราแลกเปลี่ยน|ดอกเบี้ย|ธนาคารกลาง|ธนาคารแห่งประเทศไทย|ราคาทอง|หลอกลงทุน|dólar|câmbio|Selic|juros|banco central|estafa|divisa|tipo de cambio|oro|ouro|عملة|صرف|دولار|دينار|درهم|نقد|فائدة|البنك المركزي|احتيال|ذهب|為替|円相場|ドル円|金融政策|金利|日銀|投資詐欺|金融庁|金価格|rupiah|suku bunga|penipuan|valas|OJK|Bappebti|naira|rand|shilling/i;
export function editorialGate(row:any,region:string){const text=row.title+' '+(row.summary||'');return finance.test(text)&&(region==='MY'||!!local[region]?.test(text));}
export function topicKey(x:any,row:any){
 const t=row.title+' '+(row.summary||'');if(/187/.test(t)&&/RBI|RTGS|CBI|Central Bank of India|印度中央银行/i.test(t))return '印度中央银行盗转';
 return x.event_key||x.topic.toLowerCase().replace(/[\s\p{P}]/gu,'');
}

export function regionMention(text:string,region:string){return region==='MY'?/Malaysia|Malaysian|ringgit|BNM|马来西亚|马来|令吉|林吉特|国家银行/i.test(text):!!local[region]?.test(text)||region==='KR'&&/금융감독|金融监督院/.test(text)||region==='ID'&&/泗水|Surabaya|雅加达|Jakarta|BEI|印尼/.test(text);}
