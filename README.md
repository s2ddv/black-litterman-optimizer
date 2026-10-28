# Black-Litterman Optimizer

Biblioteca Python de pesquisa para combinar um **benchmark** com opiniões sobre retornos por meio do modelo Black–Litterman. O benchmark é uma referência para o equilíbrio, **não** uma declaração das posições atuais do usuário. A saída mostra retornos esperados e pesos sem restrições; não gera ordens nem prevê retornos automaticamente.

## Executar

Requer Python 3.10+ e NumPy. Na raiz do projeto:

```bash
python -m pip install -e .
bl-optimizer examples/small.json
```

Também é possível executar sem instalar o pacote, se NumPy já estiver disponível:

```bash
PYTHONPATH=src python -m black_litterman.cli examples/small.json
PYTHONPATH=src python -m unittest discover -s tests -v
```

`examples/small.json` contém três classes de ativos e oito observações **sintéticas**, escolhidas apenas para tornar a execução reproduzível. Seus números não são dados do artigo nem evidência de desempenho.

## Arquivo de entrada

O formato é JSON; copie `examples/small.json` e altere os campos. A ordem em `assets` determina a ordem dos pesos, das colunas de `historical_returns` e das linhas e colunas de `covariance`.

| Campo | Significado |
| --- | --- |
| `assets` | Lista de nomes únicos dos ativos. |
| `frequency` | `monthly` ou `annual`. Todos os retornos, opiniões, taxa livre de risco e covariância devem estar na **mesma frequência**. Não há anualização implícita. |
| `historical_returns` | Matriz observações × ativos de retornos **simples totais**, em decimais (ex.: `0.01` = 1% no período), em ordem cronológica. Pelo menos `max(3, N+1)` observações. A covariância amostral usa `ddof=1`. |
| `covariance` | Alternativa a `historical_returns`: matriz N × N da covariância de retornos simples **por período**, em unidades decimais ao quadrado. Forneça exatamente um dos dois campos. Deve ser simétrica e definida positiva. |
| `benchmark_weights` | Frações não negativas que somam 1. Benchmark de referência para a otimização reversa; não são posições atuais. |
| `risk_aversion` | Coeficiente positivo e adimensional `λ`. Sua escolha define a escala do prêmio de risco implícito. |
| `tau` | Escalar positivo `τ` para a incerteza do prior. Na calibração implementada de Idzorek, `Ω` escala com `τ` e os retornos posteriores não mudam se só `τ` mudar. |
| `risk_free_rate` | Retorno simples livre de risco por período, decimal, usado para converter opinião absoluta de retorno total em excesso. |
| `views` | Lista opcional de opiniões, cada uma com `name`, `coefficients`, `expected_return`, `confidence` e `return_type`. |

Cada opinião especifica `P_k μ = Q_k`. Em `coefficients`, uma opinião absoluta usa coeficientes que somam **1** (por exemplo, `{"A": 1}`); uma relativa usa coeficientes que somam **0** (por exemplo, `{"A": 1, "B": -1}` significa A menos B). É possível expressar médias ponderadas com os mesmos critérios. `expected_return` é decimal por período e `return_type` é `"excess"` ou `"total"` (padrão: `"excess"`). Para uma opinião absoluta total, o programa subtrai a taxa livre de risco; em uma relativa, a taxa se cancela. `confidence` vai de `0` a `1`, não de `0` a `100`: `0.6` significa 60%.

Se você fornecer retornos históricos, a biblioteca usa **somente sua covariância**, não a média histórica como previsão. Ela exige matriz definida positiva para que os pesos sem restrições sejam únicos. Amostras curtas ou ativos quase idênticos podem exigir uma estimativa de covariância regularizada fornecida pelo usuário.

## Cálculo e interpretação

Com `Σ` representando a covariância por período, `w_b` os pesos do benchmark e `λ` a aversão ao risco, o retorno **excedente** implícito é `Π = λΣw_b`. Cada opinião é uma linha de `P` e um alvo em `Q`. O posterior é calculado pela forma estável `μ_BL = Π + τΣPᵀ(PτΣPᵀ + Ω)⁺(Q − PΠ)`, onde `⁺` é a pseudoinversa para tolerar opiniões exatas redundantes e coerentes. Os pesos sem restrições são `w_BL = Σ⁻¹μ_BL / λ`. Retornos totais esperados são os excessos mostrados mais a taxa livre de risco.

Para cada opinião isolada, o procedimento de Idzorek usa o tilt que ela causaria a 100% de confiança e define o alvo `w_b + c(w_100 − w_b)`. Nesse caso de uma opinião linear, minimizar o erro quadrático entre o peso produzido e o alvo tem solução exata `ω_k = τ(p_kΣp_kᵀ)(1−c)/c` para `0 < c < 1`. A implementação aplica essa solução diretamente, sem materializar o tilt isolado. Os `ω_k` formam a diagonal de `Ω`. Isso reproduz os passos 1–7 de calibração **isolada** do artigo por solução algébrica, sem otimizador numérico. Em conjunto, opiniões sobrepostas interagem e seus tilts finais não precisam ser exatamente `c` vezes os tilts isolados.

Confiança **0%** remove a opinião, equivalente ao limite `ω→∞`; **100%** fixa `ω=0` e exige que a opinião seja satisfeita exatamente. Opiniões exatas incompatíveis geram erro. Opiniões divergentes com confiança finita são combinadas conforme suas incertezas; quando duas usam os mesmos coeficientes e alvos diferentes, a saída avisa que há um compromisso. Confiança é uma escolha subjetiva de intensidade do tilt, **não** a probabilidade de a opinião estar correta.

A tabela da saída apresenta, para cada ativo, o retorno de equilíbrio e o posterior **em excesso por período**, os pesos do benchmark e do resultado, e a mudança em **pontos percentuais**. A soma dos pesos do resultado pode diferir de 100%, e pesos negativos são possíveis, porque a solução é sem restrição de orçamento, alavancagem ou venda a descoberto. A saída também mostra `λ`, `τ`, taxa livre de risco, origem da covariância, opiniões ativas e `ω`.

## Referência metodológica e alcance da reprodução

Thomas M. Idzorek, [*A Step-by-Step Guide to the Black-Litterman Model: Incorporating User-Specified Confidence Levels*](https://people.duke.edu/~charvey/Teaching/BA453_2005/Idzorek_onBL.pdf), rascunho de 20 de julho de 2004.

- Seção 1.1, fórmulas (1) e (2): equilíbrio `Π = λΣw_b` e pesos sem restrições.
- Seção 2.1, fórmula (3): combinação dos retornos de equilíbrio com as opiniões.
- Seção 3.2, fórmulas (12)–(19): tilt isolado a 100%, alvo escalado pela confiança e calibração diagonal de `Ω`.
- **Reprodução numérica testada:** a Tabela 1, coluna `Π`, usando as oito classes, os pesos da Tabela 2, a covariância da Tabela 5 e `λ≈3.07` informados no artigo. O teste usa tolerância de 0,02 ponto percentual porque as entradas e os resultados publicados são arredondados. Também verifica que, sem opiniões, os pesos voltam ao benchmark.

**Não foi reproduzido fielmente** o portfólio completo de três opiniões das Tabelas 6–9 nem as figuras do artigo: a primeira versão testa a coluna de equilíbrio e a propriedade matemática da calibração isolada. O exemplo executável de três ativos é sintético e independente. A covariância histórica, `λ`, as opiniões e as confianças são premissas de pesquisa; resultados são sensíveis a elas. Esta versão não inclui restrições de carteira, custos de transação, avaliação histórica, interface web ou execução de ordens. Esses componentes podem ser adicionados sobre os módulos de entrada, modelo e apresentação existentes.
