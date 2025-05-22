/**
 * Conditions.js - Functionality for managing conditional reports
 */

// Condition object to manage rule building
const ConditionBuilder = {
    // Condition data structure
    conditionData: {
        logic: 'AND',
        rules: []
    },

    // Available metrics for conditions
    availableMetrics: [
        { id: 'Cost', name: 'Cost', unit: '₽' },
        { id: 'Clicks', name: 'Clicks', unit: '' },
        { id: 'Impressions', name: 'Impressions', unit: '' },
        { id: 'Ctr', name: 'CTR', unit: '%' },
        { id: 'Conversions', name: 'Conversions', unit: '' },
        { id: 'ConversionRate', name: 'Conversion Rate', unit: '%' },
        { id: 'CostPerConversion', name: 'Cost per Conversion', unit: '₽' }
    ],

    // Available operators
    operators: [
        { id: '>', name: 'greater than', symbol: '>' },
        { id: '>=', name: 'greater than or equal to', symbol: '≥' },
        { id: '<', name: 'less than', symbol: '<' },
        { id: '<=', name: 'less than or equal to', symbol: '≤' },
        { id: '==', name: 'equal to', symbol: '=' }
    ],

    /**
     * Initialize the condition builder
     * @param {string} existingConditionJson - Optional JSON string of existing condition
     */
    init: function(existingConditionJson = null) {
        // Set up event listeners
        document.getElementById('addRuleBtn')?.addEventListener('click', this.addRule.bind(this));
        document.getElementById('logicToggle')?.addEventListener('change', this.toggleLogic.bind(this));
        
        // If editing an existing condition, load it
        if (existingConditionJson) {
            try {
                this.conditionData = JSON.parse(existingConditionJson);
                
                // Update logic toggle
                const logicToggle = document.getElementById('logicToggle');
                if (logicToggle) {
                    logicToggle.checked = (this.conditionData.logic === 'OR');
                }
                
                // Render existing rules
                this.renderRules();
            } catch (e) {
                console.error('Error parsing condition JSON:', e);
                // Initialize with empty condition
                this.conditionData = { logic: 'AND', rules: [] };
            }
        } else {
            // Add first empty rule
            this.addRule();
        }
        
        // Update form input with JSON
        this.updateFormInput();
    },

    /**
     * Toggle between AND/OR logic
     * @param {Event} event - Change event from toggle input
     */
    toggleLogic: function(event) {
        this.conditionData.logic = event.target.checked ? 'OR' : 'AND';
        this.updateLogicLabel();
        this.updateFormInput();
    },

    /**
     * Update the logic label text
     */
    updateLogicLabel: function() {
        const logicLabel = document.getElementById('logicLabel');
        if (logicLabel) {
            logicLabel.textContent = this.conditionData.logic === 'AND' 
                ? 'All conditions must be met (AND)' 
                : 'Any condition can be met (OR)';
        }
    },

    /**
     * Add a new rule to the condition
     */
    addRule: function() {
        // Create a new rule with default values
        const newRule = {
            id: Date.now(), // Unique ID for DOM manipulation
            metric: 'Cost',
            operator: '>',
            value: 1000
        };
        
        // Add to rules array
        this.conditionData.rules.push(newRule);
        
        // Render the rule
        this.renderRule(newRule);
        
        // Update the hidden form input
        this.updateFormInput();
    },

    /**
     * Remove a rule from the condition
     * @param {number} ruleId - ID of the rule to remove
     */
    removeRule: function(ruleId) {
        // Remove rule from data
        this.conditionData.rules = this.conditionData.rules.filter(rule => rule.id !== ruleId);
        
        // Remove rule from DOM
        document.getElementById(`rule-${ruleId}`)?.remove();
        
        // Update the hidden form input
        this.updateFormInput();
        
        // If no rules left, add an empty one
        if (this.conditionData.rules.length === 0) {
            this.addRule();
        }
    },

    /**
     * Render all existing rules
     */
    renderRules: function() {
        // Clear existing rules
        const rulesContainer = document.getElementById('rulesContainer');
        if (rulesContainer) {
            rulesContainer.innerHTML = '';
            
            // Render each rule
            this.conditionData.rules.forEach(rule => {
                this.renderRule(rule);
            });
        }
    },

    /**
     * Render a single rule
     * @param {Object} rule - Rule object to render
     */
    renderRule: function(rule) {
        const rulesContainer = document.getElementById('rulesContainer');
        if (!rulesContainer) return;
        
        // Create rule element
        const ruleElement = document.createElement('div');
        ruleElement.id = `rule-${rule.id}`;
        ruleElement.className = 'rule-item card mb-2';
        
        // Build metric options
        const metricOptions = this.availableMetrics.map(metric => 
            `<option value="${metric.id}" ${rule.metric === metric.id ? 'selected' : ''}>${metric.name}</option>`
        ).join('');
        
        // Build operator options
        const operatorOptions = this.operators.map(op => 
            `<option value="${op.id}" ${rule.operator === op.id ? 'selected' : ''}>${op.name}</option>`
        ).join('');
        
        // Get unit for the currently selected metric
        const metric = this.availableMetrics.find(m => m.id === rule.metric);
        const unit = metric ? metric.unit : '';
        
        // Build rule HTML
        ruleElement.innerHTML = `
            <div class="card-body py-2">
                <div class="d-flex align-items-center">
                    <div class="flex-grow-1">
                        <div class="row g-2">
                            <div class="col-md-3">
                                <select class="form-select metric-select" data-rule-id="${rule.id}">
                                    ${metricOptions}
                                </select>
                            </div>
                            <div class="col-md-3">
                                <select class="form-select operator-select" data-rule-id="${rule.id}">
                                    ${operatorOptions}
                                </select>
                            </div>
                            <div class="col-md-3">
                                <div class="input-group">
                                    <input type="number" class="form-control value-input" data-rule-id="${rule.id}" value="${rule.value}" min="0" step="any">
                                    <span class="input-group-text metric-unit">${unit}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="ms-2">
                        <button type="button" class="btn btn-sm btn-outline-danger remove-rule-btn" data-rule-id="${rule.id}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Add rule to container
        rulesContainer.appendChild(ruleElement);
        
        // Add event listeners
        ruleElement.querySelector('.metric-select').addEventListener('change', this.updateRuleMetric.bind(this));
        ruleElement.querySelector('.operator-select').addEventListener('change', this.updateRuleOperator.bind(this));
        ruleElement.querySelector('.value-input').addEventListener('input', this.updateRuleValue.bind(this));
        ruleElement.querySelector('.remove-rule-btn').addEventListener('click', (e) => {
            const ruleId = parseInt(e.currentTarget.getAttribute('data-rule-id'));
            this.removeRule(ruleId);
        });
    },

    /**
     * Update a rule's metric
     * @param {Event} event - Change event from metric select
     */
    updateRuleMetric: function(event) {
        const select = event.target;
        const ruleId = parseInt(select.getAttribute('data-rule-id'));
        const newMetric = select.value;
        
        // Update rule in data
        const ruleIndex = this.conditionData.rules.findIndex(rule => rule.id === ruleId);
        if (ruleIndex !== -1) {
            this.conditionData.rules[ruleIndex].metric = newMetric;
            
            // Update unit display
            const ruleElement = document.getElementById(`rule-${ruleId}`);
            const unitElement = ruleElement.querySelector('.metric-unit');
            const metric = this.availableMetrics.find(m => m.id === newMetric);
            
            if (unitElement && metric) {
                unitElement.textContent = metric.unit;
            }
            
            // Update form input
            this.updateFormInput();
        }
    },

    /**
     * Update a rule's operator
     * @param {Event} event - Change event from operator select
     */
    updateRuleOperator: function(event) {
        const select = event.target;
        const ruleId = parseInt(select.getAttribute('data-rule-id'));
        const newOperator = select.value;
        
        // Update rule in data
        const ruleIndex = this.conditionData.rules.findIndex(rule => rule.id === ruleId);
        if (ruleIndex !== -1) {
            this.conditionData.rules[ruleIndex].operator = newOperator;
            
            // Update form input
            this.updateFormInput();
        }
    },

    /**
     * Update a rule's value
     * @param {Event} event - Input event from value input
     */
    updateRuleValue: function(event) {
        const input = event.target;
        const ruleId = parseInt(input.getAttribute('data-rule-id'));
        const newValue = parseFloat(input.value);
        
        // Update rule in data if value is valid
        if (!isNaN(newValue)) {
            const ruleIndex = this.conditionData.rules.findIndex(rule => rule.id === ruleId);
            if (ruleIndex !== -1) {
                this.conditionData.rules[ruleIndex].value = newValue;
                
                // Update form input
                this.updateFormInput();
            }
        }
    },

    /**
     * Update the hidden form input with the current condition JSON
     */
    updateFormInput: function() {
        // Clean up the data for storage (remove ids used for DOM manipulation)
        const cleanData = {
            logic: this.conditionData.logic,
            rules: this.conditionData.rules.map(rule => ({
                metric: rule.metric,
                operator: rule.operator,
                value: rule.value
            }))
        };
        
        // Update the form input
        const conditionInput = document.getElementById('condition_json');
        if (conditionInput) {
            conditionInput.value = JSON.stringify(cleanData);
        }
        
        // Update preview
        this.updatePreview();
    },

    /**
     * Update the human-readable preview of the condition
     */
    updatePreview: function() {
        const previewElement = document.getElementById('conditionPreview');
        if (!previewElement) return;
        
        // Get the logic type (AND/OR)
        const logicType = this.conditionData.logic;
        
        // Build rule strings
        const ruleStrings = this.conditionData.rules.map(rule => {
            const metric = this.availableMetrics.find(m => m.id === rule.metric);
            const operator = this.operators.find(op => op.id === rule.operator);
            
            if (!metric || !operator) return '';
            
            // Format the value based on the metric type
            let formattedValue = rule.value.toString();
            if (metric.unit === '%') {
                formattedValue += '%';
            } else if (metric.unit === '₽') {
                formattedValue = rule.value.toLocaleString('ru-RU') + ' ₽';
            }
            
            return `<strong>${metric.name}</strong> ${operator.symbol} ${formattedValue}`;
        });
        
        // Join rule strings with appropriate logic
        let conditionText = '';
        if (ruleStrings.length === 1) {
            conditionText = ruleStrings[0];
        } else if (ruleStrings.length > 1) {
            conditionText = ruleStrings.join(` <span class="badge bg-secondary">${logicType}</span> `);
        }
        
        // Set preview HTML
        previewElement.innerHTML = conditionText;
    }
};

// Initialize the condition builder when the document is ready
document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on a condition form page
    const conditionForm = document.getElementById('conditionForm');
    
    if (conditionForm) {
        // Get existing condition JSON if editing
        const existingConditionInput = document.getElementById('condition_json');
        const existingConditionJson = existingConditionInput?.value || null;
        
        // Initialize the condition builder
        ConditionBuilder.init(existingConditionJson);
    }
});
