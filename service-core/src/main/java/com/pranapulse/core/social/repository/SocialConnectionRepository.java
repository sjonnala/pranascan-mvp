package com.pranapulse.core.social.repository;

import com.pranapulse.core.social.domain.SocialConnection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SocialConnectionRepository extends JpaRepository<SocialConnection, UUID> {

    @Query("""
            select connection
            from SocialConnection connection
            join fetch connection.requesterUser
            join fetch connection.addresseeUser
            where connection.requesterUser.id = :userId
               or connection.addresseeUser.id = :userId
            order by connection.createdAt desc
            """)
    List<SocialConnection> findAllForUser(@Param("userId") UUID userId);

    @Query("""
            select connection
            from SocialConnection connection
            join fetch connection.requesterUser
            join fetch connection.addresseeUser
            where connection.id = :connectionId
            """)
    Optional<SocialConnection> findDetailedById(@Param("connectionId") UUID connectionId);

    @Query("""
            select connection
            from SocialConnection connection
            where (connection.requesterUser.id = :leftUserId and connection.addresseeUser.id = :rightUserId)
               or (connection.requesterUser.id = :rightUserId and connection.addresseeUser.id = :leftUserId)
            """)
    Optional<SocialConnection> findConnectionBetweenUsers(
            @Param("leftUserId") UUID leftUserId,
            @Param("rightUserId") UUID rightUserId
    );
}
