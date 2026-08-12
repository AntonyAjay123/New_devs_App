from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import text


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session,
) -> Decimal:
    """Calculate monthly revenue using the property's local timezone."""

    # Retrieve the correct property using its composite identity.
    timezone_query = text("""
        SELECT timezone
        FROM properties
        WHERE id = :property_id
          AND tenant_id = :tenant_id
    """)

    timezone_result = await db_session.execute(
        timezone_query,
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
        },
    )

    timezone_name = timezone_result.scalar_one_or_none()

    if timezone_name is None:
        return Decimal("0.00")

    property_timezone = ZoneInfo(timezone_name)

    # Construct boundaries in the property's local timezone.
    local_start = datetime(
        year,
        month,
        1,
        tzinfo=property_timezone,
    )

    if month < 12:
        local_end = datetime(
            year,
            month + 1,
            1,
            tzinfo=property_timezone,
        )
    else:
        local_end = datetime(
            year + 1,
            1,
            1,
            tzinfo=property_timezone,
        )

    # Reservation timestamps are stored in UTC.
    utc_start = local_start.astimezone(timezone.utc)
    utc_end = local_end.astimezone(timezone.utc)

    revenue_query = text("""
        SELECT COALESCE(SUM(total_amount), 0)
        FROM reservations
        WHERE property_id = :property_id
          AND tenant_id = :tenant_id
          AND check_in_date >= :start_date
          AND check_in_date < :end_date
    """)

    revenue_result = await db_session.execute(
        revenue_query,
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": utc_start,
            "end_date": utc_end,
        },
    )

    total = revenue_result.scalar_one()

    return Decimal(str(total))

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Import database pool
        from app.core.database_pool import DatabasePool
        
        # Initialize pool if needed
        db_pool = DatabasePool()
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                row = result.fetchone()
                
                if row:
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        
        # Create property-specific mock data for testing when DB is unavailable
        # This ensures each property shows different figures
        mock_data = {
            'prop-001': {'total': '1000.00', 'count': 3},
            'prop-002': {'total': '4975.50', 'count': 4}, 
            'prop-003': {'total': '6100.50', 'count': 2},
            'prop-004': {'total': '1776.50', 'count': 4},
            'prop-005': {'total': '3256.00', 'count': 3}
        }
        
        mock_property_data = mock_data.get(property_id, {'total': '0.00', 'count': 0})
        
        return {
            "property_id": property_id,
            "tenant_id": tenant_id, 
            "total": mock_property_data['total'],
            "currency": "USD",
            "count": mock_property_data['count']
        }
