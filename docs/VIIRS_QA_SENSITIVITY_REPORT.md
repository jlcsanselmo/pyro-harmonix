# Sensibilidade do QA VIIRS Collection 2

## Interpretação da máscara e do QA

O guia VNP14IMG Collection 2 **versão 1.2**, seção 3.1.2, descreve classes 7, 8 e 9 da máscara como detecções de confiança baixa, nominal e alta. O campo *algorithm QA* registra a qualidade das entradas e os testes executados. A tabela 2 (p. 5) documenta os bits 0–6. Os bits 0, 1 e 2 se referem a I1, I2 e I3, com a ressalva noturna do guia. Os bits 3 e 4 indicam qualidade de I4 e I5, o bit 5 indica qualidade da geolocalização e o **bit 6 indica qualidade não nominal do canal M13** quando igual a 1. A classe 1 indica remoção bow-tie e o bit 22 indica pixel residual bow-tie. Os bits 7–18 descrevem testes, os 19–21 tratam de água e testes de persistência e os 23–31 estão reservados. [Guia NASA VNP14IMG C2 v1.2, pp. 4–5](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf#page=5)

A M13 de 750 m fornece radiância para a estimativa de FRP atribuída às detecções de 375 m. A seção 3.1.3, p. 7, descreve inclusive a possibilidade de detectar fogo com FRP nulo quando a radiância M13 satura, e FRP nulo com fundo radiométrico insuficiente. O bit 6 caracteriza a entrada M13 e pode afetar análises radiométricas que dependam dela. Por si só, ele não especifica o motivo da qualidade não nominal, a validade da presença de fogo ou o erro da FRP. A contagem experimental pode manter a classificação de presença marcada. Análises quantitativas de FRP exigiriam critérios próprios sobre M13, recuperação e preenchimento, incluindo a regra de partilha entre subpixels. A etapa analisou a presença e auditou os valores esparsos publicados de FRP. [Guia NASA C2 v1.2, tabela 3 e seção 3.1.3, pp. 6–7](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf#page=7)

## Políticas comparadas

| Política | Regra |
| --- | --- |
| Estrita | Requer bits 0–6 iguais a zero para fogo e terra válida |
| Presença com M13 sinalizada | Requer bits 0–5 iguais a zero para fogo e terra válida. Mantém a marca M13 na trilha de auditoria |

Ambas exigem terra, geolocalização nominal e geometria aceitável. Ambas excluem a classe 1, o bit 22 residual e preenchimento de *algorithm QA* como fonte de observação válida. A política exploratória aplica a mesma condição M13 a áreas com e sem fogo, evitando escolher a validade pela própria presença registrada. O campo real usa inteiro sem sinal de 32 bits. O leitor garante representação inteira de 32 bits antes de aplicar máscaras e usa o sentinela interno 0xffffffff para valores mascarados. Há testes para valor de preenchimento mascarado, inteiro originalmente assinado, bit alto, M13 isolado, M13 com I4 e bit 22.

## Resultado observado em 24/08/2024

Dos 363 centros da máscara, 362 passaram pela condição de terra, geolocalização nominal e descarte bow-tie. Entre esses, 280 tinham M13 não nominal. Quinze também tinham I4 não nominal. Com o tratamento isolado do bit 6, passam **347 centros**, ante **82** com QA estrito. Os campos esparsos por FP_line e FP_sample continham FRP positiva para os 280 marcados, o que registra um valor publicado para cada caso. Sua acurácia requer uma avaliação própria. A correspondência FIRMS preserva as classes de confiança de todos os 363 centros da máscara. [QA e atributos por centro](data/phase4/2024-08-24/firms-viirs-center-comparison.csv) · [Contagens, dimensões e FRP por bit](data/phase4/2024-08-24/geometry-and-qa-diagnostics.json)

O rastreio identificou um erro de implementação no cenário legado. Quando os bits de entrada passavam, a comparação da máscara terrestre devolvia um booleano NumPy. O classificador checava o valor pela identidade com False do Python, e deixava passar observações de outras classes mesmo quando a comparação devolvia falso. A fase 4 reproduz a situação em um cenário de controle e corrige a conversão para booleano nos cenários revisados. O cabeçalho dos grânulos geográficos confirma classe 1 como terra e classe 2 como faixa marginal de água (*Coastline*). Um centro de fogo de 2024 estava na classe 2. As áreas de fundo também mudaram depois da correção. [Atributos C2 da geolocalização](data/phase4/2024-08-24/embedded-metadata.json) · [Guia de nível 1 VIIRS, tabela 4](https://ladsweb.modaps.eosdis.nasa.gov/api/v2/content/archives/Document%20Archive/Science%20Data%20Product%20Documentation/Processing%20and%20Algorithm%20Version%20History/NASA_VIIRS_L1B_UG_August_2021.pdf)


## Efeito no suporte e na presença

A 65° em 2024, a área válida VIIRS aumentou de 5.526,16 para 5.629,88 km² com a política M13. Os centros retidos passaram de 82 para 347. Na segunda dupla a 55°, a área válida VIIRS passou de 5.797,95 para 5.800,48 km², e os centros passaram de 3 para 8. Dos 9 centros brutos de 2019, 6 continham o bit 6 e 1 deles também continha outro bit de entrada impeditivo. A sensibilidade foi definida a partir da documentação de produto, e o comportamento nas duas duplas depende de área, geometria e QA simultaneamente. [Comparação completa e mapas](SECOND_ORBITAL_PILOT_REPORT.md)
