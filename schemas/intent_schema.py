
from enum import Enum
from typing import Any, Optional

from pydantic import (
    BaseModel,
    Field,
    model_validator
)
from pydantic import field_validator

# ==================================================
# 1. ENUMS
# ==================================================

class BusinessDomain(str, Enum):
    SALES = "sales"
    CUSTOMER = "customer"
    PRODUCT = "product"
    EMPLOYEE = "employee"
    SUPPLIER = "supplier"
    SHIPPING = "shipping"
    GENERAL = "general"


class AnalysisType(str, Enum):
    SUMMARY = "summary"
    TREND = "trend"
    COMPARISON = "comparison"
    RANKING = "ranking"
    DISTRIBUTION = "distribution"
    DETAILED_ANALYSIS = "detailed_analysis"
    ANOMALY_DETECTION = "anomaly_detection"
    ROOT_CAUSE = "root_cause"


class FilterOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    BETWEEN = "between"
    IN = "in"
    CONTAINS = "contains"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class TimeGranularity(str, Enum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    NONE = "none"


# ==================================================
# 2. FILTER REQUIREMENTS
# ==================================================

class FilterRequirement(BaseModel):


    attribute: str = Field(
        description="Business attribute or database field to filter."
    )

    operator: FilterOperator

    value: Optional[str] = None
    second_value: Optional[str] = None

    @model_validator(mode="after")
    def validate_filter_values(self):

        if self.operator == FilterOperator.BETWEEN:

            if self.value is None or self.second_value is None:
                raise ValueError(
                    "BETWEEN requires both value and second_value."
                )

        if self.operator in {
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL
        }:

            if self.value is not None or self.second_value is not None:
                raise ValueError(
                    "NULL operators must not contain filter values."
                )

        return self


# ==================================================
# 3. TIME REQUIREMENTS
# ==================================================

class TimeRequirement(BaseModel):


    start_date: Optional[str] = None

    end_date: Optional[str] = None

    relative_period: Optional[str] = Field(
        default=None,
        description=(
            "Examples: last month, previous quarter, "
            "current year, last 30 days."
        )
    )

    granularity: TimeGranularity = TimeGranularity.NONE

    @model_validator(mode="after")
    def validate_dates(self):

        if self.start_date and self.end_date:

            if self.start_date > self.end_date:
                raise ValueError(
                    "Start date cannot be after end date."
                )

        return self


# ==================================================
# 4. COMPARISON REQUIREMENTS
# ==================================================

class ComparisonRequirement(BaseModel):


    comparison_type: str = Field(
        description=(
            "Examples: year_over_year, month_over_month, "
            "quarter_over_quarter, category_comparison."
        )
    )

    comparison_dimension: Optional[str] = None

    baseline_period: Optional[str] = None

    target_period: Optional[str] = None


# ==================================================
# 5. MAIN BUSINESS INTENT
# ==================================================

class BusinessIntent(BaseModel):
    """
    Structured output of the Intent Understanding Agent.

    Converts natural-language business questions into
    structured analytical requirements.
    """



    # Original question
    original_question: str = Field(
        description="Exact question asked by the business user."
    )

    # Business objective
    business_domain: BusinessDomain

    business_objective: str = Field(
        description="Main business problem or objective."
    )

    # KPIs and dimensions
    metrics: list[str] = Field(
        default_factory=list,
        description="KPIs such as revenue, profit, quantity, order count."
    )

    dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "Grouping attributes such as product, category, "
            "customer, employee, country or region."
        )
    )

    # Filters
    filters: list[FilterRequirement] = Field(
        default_factory=list
    )

    # Time requirements
    time_requirement: Optional[TimeRequirement] = None

    # Comparisons
    comparison: Optional[ComparisonRequirement] = None

    requires_period_comparison: bool = Field(
        default=False,
        description=(
            "Whether the analysis requires comparing two "
            "or more time periods."
        )
    )

    # Analysis requirements
    analysis_types: list[AnalysisType] = Field(
        default_factory=list
    )

    # Root cause investigation
    investigation_required: bool = Field(
        default=False,
        description=(
            "True when the user asks why a business metric "
            "changed or what caused a business problem."
        )
    )

    investigation_dimensions: list[str] = Field(
        default_factory=list,
        description=(
            "Potential business dimensions to investigate, "
            "such as product, category, customer, region, "
            "employee or shipping."
        )
    )

    # Output requirements
    result_limit: Optional[int] = Field(
    default=None,
    description="Top-N limit requested by the user, e.g. 5 for 'top 5'. Must be positive."
    )

    sorting_preference: Optional[str] = None

    requires_aggregation: bool = False

    requires_visualization: bool = False

    # Clarification handling
    needs_clarification: bool = False

    clarification_question: Optional[str] = None

    @field_validator("result_limit")
    @classmethod
    def validate_result_limit(cls, value):
        if value is not None and value <= 0:
            return None
        return value

    @field_validator("analysis_types", mode="before")
    @classmethod
    def normalize_analysis_types(cls, value):
        if isinstance(value, list):
            return [
                item.lower() if isinstance(item, str) else item
                for item in value
            ]
        return value

    @model_validator(mode="after")
    def validate_clarification(self):

        if self.needs_clarification and not self.clarification_question:
            raise ValueError(
                "A clarification question is required "
                "when needs_clarification is True."
            )

        if not self.needs_clarification and self.clarification_question:
            raise ValueError(
                "Clarification question must be empty "
                "when clarification is not required."
            )

        if (self.investigation_required
            and AnalysisType.ROOT_CAUSE not in self.analysis_types):
            self.analysis_types.append(AnalysisType.ROOT_CAUSE)

        if (self.requires_period_comparison
                and AnalysisType.COMPARISON not in self.analysis_types):
            self.analysis_types.append(AnalysisType.COMPARISON)

        return self
