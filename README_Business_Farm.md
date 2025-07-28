# Business Analysis Agent Farm 🏢

En avanceret multi-agent business intelligence orchestrator bygget på Claude Code Agent Farm arkitekturen. Systemet analyserer Excel data og genererer omfattende business cases med specialiserede AI-agenter.

## 🎯 Formål

Konverterer Kop&Kande's Excel-baserede beregninger til en dybtgående business case analyse for implementering af 25 DKK gebyr på Click & Collect ordrer under 150 DKK.

## 🔧 System Arkitektur

### Agent Specialiseringer

1. **Financial Modeling** (4 agenter)
   - Unit economics og ROI modellering
   - Cash flow projektioner og NPV beregninger
   - Break-even analyse og følsomhedsanalyse

2. **Customer Analytics** (3 agenter)
   - Kundesegmentering og adfærdsanalyse
   - Customer Lifetime Value (CLV) modellering
   - Churn prediction og retention strategier

3. **Pricing Strategy** (3 agenter)
   - Pricing elasticity modellering
   - Konkurrendeanalyse og benchmarking
   - Value-based pricing optimering

4. **Market Intelligence** (2 agenter)
   - Competitive intelligence
   - Markedsstørrelse og trend analyse
   - Industry research og positioning

5. **Operations Analytics** (3 agenter)
   - Process optimization
   - Efficiency analyse og capacity planning
   - Operationelle metrics

6. **Risk Assessment** (2 agenter)
   - Risiko identifikation og modellering
   - Scenarie analyse og mitigation
   - Sensitivity testing

7. **Strategic Planning** (2 agenter)
   - Strategic framework analyse
   - Growth planning og positioning
   - Implementation roadmaps

8. **Data Integration** (2 agenter)
   - Data harmonization og quality assessment
   - Integration analyse og insights synthesis

9. **QA Validation** (2 agenter)
   - Analysis validation og consistency checking
   - Methodology review og quality assurance

10. **Synthesis Coordination** (2 agenter)
    - Multi-agent insight integration
    - Executive reporting og strategic communication

## 📁 Fil Struktur

```
claude_code_agent_farm/
├── business_analysis_farm.py          # Hoved orchestrator
├── kop_kande_config.json             # Konfiguration for Kop&Kande case
├── prompts/
│   ├── business_analysis_base_prompt.md
│   ├── financial_modeling_prompt.md
│   ├── customer_analytics_prompt.md
│   └── pricing_strategy_prompt.md
├── test_business_farm.py             # Test suite
├── simple_test.py                    # Basic validering
└── README_Business_Farm.md           # Denne dokumentation
```

## 🚀 Installation

### 1. Dependencies
```bash
# Via pip (if allowed)
pip3 install pandas openpyxl typer rich

# Via brew (macOS)
brew install python
pip3 install --user pandas openpyxl typer rich

# Via virtual environment (anbefalet)
python3 -m venv business_env
source business_env/bin/activate
pip install pandas openpyxl typer rich
```

### 2. Verificer Installation
```bash
python3 simple_test.py
```

## 💼 Brug

### Basis Kommando
```bash
python3 business_analysis_farm.py \
  --path /path/to/project \
  --excel-files "/Users/nikolailind/Downloads/Beregning C&C.xlsx,/Users/nikolailind/Downloads/business case endless aisles 2023.xlsx" \
  --config kop_kande_config.json \
  --agents 25
```

### Med Konfigurationsfil
```bash
python3 business_analysis_farm.py \
  --path . \
  --config kop_kande_config.json
```

### Tilpasset Analyse
```bash
python3 business_analysis_farm.py \
  --path . \
  --agents 15 \
  --session "custom_analysis" \
  --language danish \
  --analysis-type "pricing_optimization" \
  --excel-files "data.xlsx"
```

## ⚙️ Konfiguration

### kop_kande_config.json
```json
{
  "analysis_type": "business_case_development",
  "language": "danish", 
  "agents": 25,
  "excel_files": ["Beregning C&C.xlsx"],
  "business_context": {
    "company": "Kop&Kande",
    "proposed_fee": "25 DKK",
    "threshold": "150 DKK",
    "current_cost": "336,000 DKK annually"
  },
  "agent_specializations": {
    "financial_modeling": 4,
    "customer_analytics": 3,
    "pricing_strategy": 3
  }
}
```

## 📊 Excel Data Proces

### Understøttede Data Typer
- **Finansielle metrics**: Revenue, costs, margins, ROI
- **Kunde data**: Segmenter, ordrestørrelser, frequency
- **Operationelle data**: Volumes, processes, efficiency
- **Markedsdata**: Competitors, pricing, trends

### Data Udtrækning
Systemet analyserer automatisk Excel sheets og identificerer:
- Finansielle kolonner (cost, revenue, dkk)
- Kunde metrics (customer, order, frequency)
- Operationelle data (volume, capacity, time)

## 🎛️ Monitoring Dashboard

Real-time status for alle agenter:
- Agent type og specialisering
- Current task og progress
- Completed analyses count
- Generated insights count
- Error tracking og restart logic

## 🔄 Workflow

1. **Excel Processing**: Indlæs og analyser Excel filer
2. **Task Generation**: Opret specialiserede analyse opgaver
3. **Agent Launch**: Start tmux session med 25 agenter
4. **Parallel Analysis**: Agenter arbejder samtidigt på deres specialeområder
5. **Insight Synthesis**: Koordination og integration af resultater
6. **Executive Reporting**: Generering af business case rapport

## 📈 Output Format

### Executive Summary (Dansk)
- Kort sammenfatning af hovedresultater
- ROI analyse og financial projections
- Risk assessment og mitigation strategier
- Implementation roadmap

### Detaljeret Analyse
- Kvantitative modeller og beregninger
- Customer segmentation insights
- Pricing strategy anbefalinger
- Competitive positioning
- Scenario planning

## 🚨 Troubleshooting

### Almindelige Problemer

1. **ModuleNotFoundError**
   ```bash
   pip3 install --user pandas openpyxl typer rich
   ```

2. **Excel fil ikke fundet**
   - Check absolut path til Excel filer
   - Verificer fil permissions

3. **tmux session conflicts**
   ```bash
   tmux kill-session -t business_agents
   ```

4. **Agent startup errors**
   - Check Claude Code installation
   - Verificer PATH og permissions

### Debug Mode
```bash
python3 business_analysis_farm.py \
  --path . \
  --config kop_kande_config.json \
  --no-monitor \
  --agents 5
```

## 🎯 Kop&Kande Specific Case

### Business Context
- **Initiativ**: Click & Collect gebyr på 25 DKK
- **Scope**: Ordrer under 150 DKK
- **Current State**: 15.9% af C&C ordrer under 130 DKK
- **Annual Cost**: 336,000 DKK
- **Objective**: Determine ROI og customer impact

### Key Questions Analyseret
1. Hvad er den optimale gebyr struktur?
2. Hvordan reagerer forskellige kunde segmenter?
3. Hvad er break-even point?
4. Hvilke risici er der ved implementering?
5. Hvordan påvirker det competitive positioning?

### Expected Deliverables
- Comprehensive ROI analysis
- Customer segmentation insights
- Pricing strategy recommendations  
- Risk mitigation plan
- Implementation roadmap
- Executive summary på dansk

## 🤝 Support

For problemer eller spørgsmål relateret til Business Analysis Farm:
1. Check simple_test.py output
2. Review log files i tmux session
3. Validate Excel data format
4. Test med mindre agent count først

## 📝 Notes

Dette system er bygget specifikt til Kop&Kande business case, men kan tilpasses til andre business intelligence opgaver ved at:
1. Modificere agent specializations
2. Tilpasse prompt templates  
3. Ændre Excel processing logic
4. Opdatere business context configuration